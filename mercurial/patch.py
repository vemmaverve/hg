# patch.py - patch file parsing routines
#
# Copyright 2006 Brendan Cully <brendan@kublai.com>
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.

from i18n import _
from node import *
import base85, cmdutil, mdiff, util, context, revlog
import cStringIO, email.Parser, os, popen2, re, sha
import sys, tempfile, zlib

# helper functions

def copyfile(src, dst, basedir=None):
    if not basedir:
        basedir = os.getcwd()

    abssrc, absdst = [os.path.join(basedir, n) for n in (src, dst)]
    if os.path.exists(absdst):
        raise util.Abort(_("cannot create %s: destination already exists") %
                         dst)

    targetdir = os.path.dirname(absdst)
    if not os.path.isdir(targetdir):
        os.makedirs(targetdir)

    util.copyfile(abssrc, absdst)

# public functions

def extract(ui, fileobj):
    '''extract patch from data read from fileobj.

    patch can be a normal patch or contained in an email message.

    return tuple (filename, message, user, date, node, p1, p2).
    Any item in the returned tuple can be None. If filename is None,
    fileobj did not contain a patch. Caller must unlink filename when done.'''

    # attempt to detect the start of a patch
    # (this heuristic is borrowed from quilt)
    diffre = re.compile(r'^(?:Index:[ \t]|diff[ \t]|RCS file: |' +
                        'retrieving revision [0-9]+(\.[0-9]+)*$|' +
                        '(---|\*\*\*)[ \t])', re.MULTILINE)

    fd, tmpname = tempfile.mkstemp(prefix='hg-patch-')
    tmpfp = os.fdopen(fd, 'w')
    try:
        msg = email.Parser.Parser().parse(fileobj)

        message = msg['Subject']
        user = msg['From']
        # should try to parse msg['Date']
        date = None
        nodeid = None
        branch = None
        parents = []

        if message:
            if message.startswith('[PATCH'):
                pend = message.find(']')
                if pend >= 0:
                    message = message[pend+1:].lstrip()
            message = message.replace('\n\t', ' ')
            ui.debug('Subject: %s\n' % message)
        if user:
            ui.debug('From: %s\n' % user)
        diffs_seen = 0
        ok_types = ('text/plain', 'text/x-diff', 'text/x-patch')

        for part in msg.walk():
            content_type = part.get_content_type()
            ui.debug('Content-Type: %s\n' % content_type)
            if content_type not in ok_types:
                continue
            payload = part.get_payload(decode=True)
            m = diffre.search(payload)
            if m:
                hgpatch = False
                ignoretext = False

                ui.debug(_('found patch at byte %d\n') % m.start(0))
                diffs_seen += 1
                cfp = cStringIO.StringIO()
                if message:
                    cfp.write(message)
                    cfp.write('\n')
                for line in payload[:m.start(0)].splitlines():
                    if line.startswith('# HG changeset patch'):
                        ui.debug(_('patch generated by hg export\n'))
                        hgpatch = True
                        # drop earlier commit message content
                        cfp.seek(0)
                        cfp.truncate()
                    elif hgpatch:
                        if line.startswith('# User '):
                            user = line[7:]
                            ui.debug('From: %s\n' % user)
                        elif line.startswith("# Date "):
                            date = line[7:]
                        elif line.startswith("# Branch "):
                            branch = line[9:]
                        elif line.startswith("# Node ID "):
                            nodeid = line[10:]
                        elif line.startswith("# Parent "):
                            parents.append(line[10:])
                    elif line == '---' and 'git-send-email' in msg['X-Mailer']:
                        ignoretext = True
                    if not line.startswith('# ') and not ignoretext:
                        cfp.write(line)
                        cfp.write('\n')
                message = cfp.getvalue()
                if tmpfp:
                    tmpfp.write(payload)
                    if not payload.endswith('\n'):
                        tmpfp.write('\n')
            elif not diffs_seen and message and content_type == 'text/plain':
                message += '\n' + payload
    except:
        tmpfp.close()
        os.unlink(tmpname)
        raise

    tmpfp.close()
    if not diffs_seen:
        os.unlink(tmpname)
        return None, message, user, date, branch, None, None, None
    p1 = parents and parents.pop(0) or None
    p2 = parents and parents.pop(0) or None
    return tmpname, message, user, date, branch, nodeid, p1, p2

GP_PATCH  = 1 << 0  # we have to run patch
GP_FILTER = 1 << 1  # there's some copy/rename operation
GP_BINARY = 1 << 2  # there's a binary patch

def readgitpatch(patchname):
    """extract git-style metadata about patches from <patchname>"""
    class gitpatch:
        "op is one of ADD, DELETE, RENAME, MODIFY or COPY"
        def __init__(self, path):
            self.path = path
            self.oldpath = None
            self.mode = None
            self.op = 'MODIFY'
            self.copymod = False
            self.lineno = 0
            self.binary = False

    # Filter patch for git information
    gitre = re.compile('diff --git a/(.*) b/(.*)')
    pf = file(patchname)
    gp = None
    gitpatches = []
    # Can have a git patch with only metadata, causing patch to complain
    dopatch = 0

    lineno = 0
    for line in pf:
        lineno += 1
        if line.startswith('diff --git'):
            m = gitre.match(line)
            if m:
                if gp:
                    gitpatches.append(gp)
                src, dst = m.group(1, 2)
                gp = gitpatch(dst)
                gp.lineno = lineno
        elif gp:
            if line.startswith('--- '):
                if gp.op in ('COPY', 'RENAME'):
                    gp.copymod = True
                    dopatch |= GP_FILTER
                gitpatches.append(gp)
                gp = None
                dopatch |= GP_PATCH
                continue
            if line.startswith('rename from '):
                gp.op = 'RENAME'
                gp.oldpath = line[12:].rstrip()
            elif line.startswith('rename to '):
                gp.path = line[10:].rstrip()
            elif line.startswith('copy from '):
                gp.op = 'COPY'
                gp.oldpath = line[10:].rstrip()
            elif line.startswith('copy to '):
                gp.path = line[8:].rstrip()
            elif line.startswith('deleted file'):
                gp.op = 'DELETE'
            elif line.startswith('new file mode '):
                gp.op = 'ADD'
                gp.mode = int(line.rstrip()[-3:], 8)
            elif line.startswith('new mode '):
                gp.mode = int(line.rstrip()[-3:], 8)
            elif line.startswith('GIT binary patch'):
                dopatch |= GP_BINARY
                gp.binary = True
    if gp:
        gitpatches.append(gp)

    if not gitpatches:
        dopatch = GP_PATCH

    return (dopatch, gitpatches)

def dogitpatch(patchname, gitpatches, cwd=None):
    """Preprocess git patch so that vanilla patch can handle it"""
    def extractbin(fp):
        i = [0] # yuck
        def readline():
            i[0] += 1
            return fp.readline().rstrip()
        line = readline()
        while line and not line.startswith('literal '):
            line = readline()
        if not line:
            return None, i[0]
        size = int(line[8:])
        dec = []
        line = readline()
        while line:
            l = line[0]
            if l <= 'Z' and l >= 'A':
                l = ord(l) - ord('A') + 1
            else:
                l = ord(l) - ord('a') + 27
            dec.append(base85.b85decode(line[1:])[:l])
            line = readline()
        text = zlib.decompress(''.join(dec))
        if len(text) != size:
            raise util.Abort(_('binary patch is %d bytes, not %d') %
                             (len(text), size))
        return text, i[0]

    pf = file(patchname)
    pfline = 1

    fd, patchname = tempfile.mkstemp(prefix='hg-patch-')
    tmpfp = os.fdopen(fd, 'w')

    try:
        for i in xrange(len(gitpatches)):
            p = gitpatches[i]
            if not p.copymod and not p.binary:
                continue

            # rewrite patch hunk
            while pfline < p.lineno:
                tmpfp.write(pf.readline())
                pfline += 1

            if p.binary:
                text, delta = extractbin(pf)
                if not text:
                    raise util.Abort(_('binary patch extraction failed'))
                pfline += delta
                if not cwd:
                    cwd = os.getcwd()
                absdst = os.path.join(cwd, p.path)
                basedir = os.path.dirname(absdst)
                if not os.path.isdir(basedir):
                    os.makedirs(basedir)
                out = file(absdst, 'wb')
                out.write(text)
                out.close()
            elif p.copymod:
                copyfile(p.oldpath, p.path, basedir=cwd)
                tmpfp.write('diff --git a/%s b/%s\n' % (p.path, p.path))
                line = pf.readline()
                pfline += 1
                while not line.startswith('--- a/'):
                    tmpfp.write(line)
                    line = pf.readline()
                    pfline += 1
                tmpfp.write('--- a/%s\n' % p.path)

        line = pf.readline()
        while line:
            tmpfp.write(line)
            line = pf.readline()
    except:
        tmpfp.close()
        os.unlink(patchname)
        raise

    tmpfp.close()
    return patchname

def patch(patchname, ui, strip=1, cwd=None, files={}):
    """apply the patch <patchname> to the working directory.
    a list of patched files is returned"""

    # helper function
    def __patch(patchname):
        """patch and updates the files and fuzz variables"""
        fuzz = False

        args = []
        patcher = ui.config('ui', 'patch')
        if not patcher:
            patcher = util.find_in_path('gpatch', os.environ.get('PATH', ''),
                                        'patch')
            if util.needbinarypatch():
                args.append('--binary')
                                    
        if cwd:
            args.append('-d %s' % util.shellquote(cwd))
        fp = os.popen('%s %s -p%d < %s' % (patcher, ' '.join(args), strip,
                                           util.shellquote(patchname)))

        for line in fp:
            line = line.rstrip()
            ui.note(line + '\n')
            if line.startswith('patching file '):
                pf = util.parse_patch_output(line)
                printed_file = False
                files.setdefault(pf, (None, None))
            elif line.find('with fuzz') >= 0:
                fuzz = True
                if not printed_file:
                    ui.warn(pf + '\n')
                    printed_file = True
                ui.warn(line + '\n')
            elif line.find('saving rejects to file') >= 0:
                ui.warn(line + '\n')
            elif line.find('FAILED') >= 0:
                if not printed_file:
                    ui.warn(pf + '\n')
                    printed_file = True
                ui.warn(line + '\n')
        code = fp.close()
        if code:
            raise util.Abort(_("patch command failed: %s") %
                             util.explain_exit(code)[0])
        return fuzz

    (dopatch, gitpatches) = readgitpatch(patchname)
    for gp in gitpatches:
        files[gp.path] = (gp.op, gp)

    fuzz = False
    if dopatch:
        filterpatch = dopatch & (GP_FILTER | GP_BINARY)
        if filterpatch:
            patchname = dogitpatch(patchname, gitpatches, cwd=cwd)
        try:
            if dopatch & GP_PATCH:
                fuzz = __patch(patchname)
        finally:
            if filterpatch:
                os.unlink(patchname)

    return fuzz

def diffopts(ui, opts={}, untrusted=False):
    def get(key, name=None):
        return (opts.get(key) or
                ui.configbool('diff', name or key, None, untrusted=untrusted))
    return mdiff.diffopts(
        text=opts.get('text'),
        git=get('git'),
        nodates=get('nodates'),
        showfunc=get('show_function', 'showfunc'),
        ignorews=get('ignore_all_space', 'ignorews'),
        ignorewsamount=get('ignore_space_change', 'ignorewsamount'),
        ignoreblanklines=get('ignore_blank_lines', 'ignoreblanklines'))

def updatedir(ui, repo, patches, wlock=None):
    '''Update dirstate after patch application according to metadata'''
    if not patches:
        return
    copies = []
    removes = {}
    cfiles = patches.keys()
    cwd = repo.getcwd()
    if cwd:
        cfiles = [util.pathto(repo.root, cwd, f) for f in patches.keys()]
    for f in patches:
        ctype, gp = patches[f]
        if ctype == 'RENAME':
            copies.append((gp.oldpath, gp.path, gp.copymod))
            removes[gp.oldpath] = 1
        elif ctype == 'COPY':
            copies.append((gp.oldpath, gp.path, gp.copymod))
        elif ctype == 'DELETE':
            removes[gp.path] = 1
    for src, dst, after in copies:
        if not after:
            copyfile(src, dst, repo.root)
        repo.copy(src, dst, wlock=wlock)
    removes = removes.keys()
    if removes:
        removes.sort()
        repo.remove(removes, True, wlock=wlock)
    for f in patches:
        ctype, gp = patches[f]
        if gp and gp.mode:
            x = gp.mode & 0100 != 0
            dst = os.path.join(repo.root, gp.path)
            # patch won't create empty files
            if ctype == 'ADD' and not os.path.exists(dst):
                repo.wwrite(gp.path, '', x and 'x' or '')
            else:
                util.set_exec(dst, x)
    cmdutil.addremove(repo, cfiles, wlock=wlock)
    files = patches.keys()
    files.extend([r for r in removes if r not in files])
    files.sort()

    return files

def b85diff(fp, to, tn):
    '''print base85-encoded binary diff'''
    def gitindex(text):
        if not text:
            return '0' * 40
        l = len(text)
        s = sha.new('blob %d\0' % l)
        s.update(text)
        return s.hexdigest()

    def fmtline(line):
        l = len(line)
        if l <= 26:
            l = chr(ord('A') + l - 1)
        else:
            l = chr(l - 26 + ord('a') - 1)
        return '%c%s\n' % (l, base85.b85encode(line, True))

    def chunk(text, csize=52):
        l = len(text)
        i = 0
        while i < l:
            yield text[i:i+csize]
            i += csize

    tohash = gitindex(to)
    tnhash = gitindex(tn)
    if tohash == tnhash:
        return ""

    # TODO: deltas
    ret = ['index %s..%s\nGIT binary patch\nliteral %s\n' %
           (tohash, tnhash, len(tn))]
    for l in chunk(zlib.compress(tn)):
        ret.append(fmtline(l))
    ret.append('\n')
    return ''.join(ret)

def diff(repo, node1=None, node2=None, files=None, match=util.always,
         fp=None, changes=None, opts=None):
    '''print diff of changes to files between two nodes, or node and
    working directory.

    if node1 is None, use first dirstate parent instead.
    if node2 is None, compare node1 with working directory.'''

    if opts is None:
        opts = mdiff.defaultopts
    if fp is None:
        fp = repo.ui

    if not node1:
        node1 = repo.dirstate.parents()[0]

    ccache = {}
    def getctx(r):
        if r not in ccache:
            ccache[r] = context.changectx(repo, r)
        return ccache[r]

    flcache = {}
    def getfilectx(f, ctx):
        flctx = ctx.filectx(f, filelog=flcache.get(f))
        if f not in flcache:
            flcache[f] = flctx._filelog
        return flctx

    # reading the data for node1 early allows it to play nicely
    # with repo.status and the revlog cache.
    ctx1 = context.changectx(repo, node1)
    # force manifest reading
    man1 = ctx1.manifest()
    date1 = util.datestr(ctx1.date())

    if not changes:
        changes = repo.status(node1, node2, files, match=match)[:5]
    modified, added, removed, deleted, unknown = changes

    if not modified and not added and not removed:
        return

    if node2:
        ctx2 = context.changectx(repo, node2)
    else:
        ctx2 = context.workingctx(repo)
    man2 = ctx2.manifest()

    # returns False if there was no rename between ctx1 and ctx2
    # returns None if the file was created between ctx1 and ctx2
    # returns the (file, node) present in ctx1 that was renamed to f in ctx2
    def renamed(f):
        startrev = ctx1.rev()
        c = ctx2
        crev = c.rev()
        if crev is None:
            crev = repo.changelog.count()
        orig = f
        while crev > startrev:
            if f in c.files():
                try:
                    src = getfilectx(f, c).renamed()
                except revlog.LookupError:
                    return None
                if src:
                    f = src[0]
            crev = c.parents()[0].rev()
            # try to reuse
            c = getctx(crev)
        if f not in man1:
            return None
        if f == orig:
            return False
        return f

    if repo.ui.quiet:
        r = None
    else:
        hexfunc = repo.ui.debugflag and hex or short
        r = [hexfunc(node) for node in [node1, node2] if node]

    if opts.git:
        copied = {}
        for f in added:
            src = renamed(f)
            if src:
                copied[f] = src
        srcs = [x[1] for x in copied.items()]

    all = modified + added + removed
    all.sort()
    gone = {}

    for f in all:
        to = None
        tn = None
        dodiff = True
        header = []
        if f in man1:
            to = getfilectx(f, ctx1).data()
        if f not in removed:
            tn = getfilectx(f, ctx2).data()
        if opts.git:
            def gitmode(x):
                return x and '100755' or '100644'
            def addmodehdr(header, omode, nmode):
                if omode != nmode:
                    header.append('old mode %s\n' % omode)
                    header.append('new mode %s\n' % nmode)

            a, b = f, f
            if f in added:
                mode = gitmode(man2.execf(f))
                if f in copied:
                    a = copied[f]
                    omode = gitmode(man1.execf(a))
                    addmodehdr(header, omode, mode)
                    if a in removed and a not in gone:
                        op = 'rename'
                        gone[a] = 1
                    else:
                        op = 'copy'
                    header.append('%s from %s\n' % (op, a))
                    header.append('%s to %s\n' % (op, f))
                    to = getfilectx(a, ctx1).data()
                else:
                    header.append('new file mode %s\n' % mode)
                if util.binary(tn):
                    dodiff = 'binary'
            elif f in removed:
                if f in srcs:
                    dodiff = False
                else:
                    mode = gitmode(man1.execf(f))
                    header.append('deleted file mode %s\n' % mode)
            else:
                omode = gitmode(man1.execf(f))
                nmode = gitmode(man2.execf(f))
                addmodehdr(header, omode, nmode)
                if util.binary(to) or util.binary(tn):
                    dodiff = 'binary'
            r = None
            header.insert(0, 'diff --git a/%s b/%s\n' % (a, b))
        if dodiff:
            if dodiff == 'binary':
                text = b85diff(fp, to, tn)
            else:
                text = mdiff.unidiff(to, date1,
                                    # ctx2 date may be dynamic
                                    tn, util.datestr(ctx2.date()),
                                    f, r, opts=opts)
            if text or len(header) > 1:
                fp.write(''.join(header))
            fp.write(text)

def export(repo, revs, template='hg-%h.patch', fp=None, switch_parent=False,
           opts=None):
    '''export changesets as hg patches.'''

    total = len(revs)
    revwidth = max([len(str(rev)) for rev in revs])

    def single(rev, seqno, fp):
        ctx = repo.changectx(rev)
        node = ctx.node()
        parents = [p.node() for p in ctx.parents() if p]
        branch = ctx.branch()
        if switch_parent:
            parents.reverse()
        prev = (parents and parents[0]) or nullid

        if not fp:
            fp = cmdutil.make_file(repo, template, node, total=total,
                                   seqno=seqno, revwidth=revwidth)
        if fp != sys.stdout and hasattr(fp, 'name'):
            repo.ui.note("%s\n" % fp.name)

        fp.write("# HG changeset patch\n")
        fp.write("# User %s\n" % ctx.user())
        fp.write("# Date %d %d\n" % ctx.date())
        if branch and (branch != 'default'):
            fp.write("# Branch %s\n" % branch)
        fp.write("# Node ID %s\n" % hex(node))
        fp.write("# Parent  %s\n" % hex(prev))
        if len(parents) > 1:
            fp.write("# Parent  %s\n" % hex(parents[1]))
        fp.write(ctx.description().rstrip())
        fp.write("\n\n")

        diff(repo, prev, node, fp=fp, opts=opts)
        if fp not in (sys.stdout, repo.ui):
            fp.close()

    for seqno, rev in enumerate(revs):
        single(rev, seqno+1, fp)

def diffstat(patchlines):
    if not util.find_in_path('diffstat', os.environ.get('PATH', '')):
        return
    fd, name = tempfile.mkstemp(prefix="hg-patchbomb-", suffix=".txt")
    try:
        p = popen2.Popen3('diffstat -p1 -w79 2>/dev/null > ' + name)
        try:
            for line in patchlines: print >> p.tochild, line
            p.tochild.close()
            if p.wait(): return
            fp = os.fdopen(fd, 'r')
            stat = []
            for line in fp: stat.append(line.lstrip())
            last = stat.pop()
            stat.insert(0, last)
            stat = ''.join(stat)
            if stat.startswith('0 files'): raise ValueError
            return stat
        except: raise
    finally:
        try: os.unlink(name)
        except: pass
