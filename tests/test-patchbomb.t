  are you sure you want to send (yn)? abort: patchbomb canceled
  > --config progress.width=60 2>&1 | \
  > python "$TESTDIR/filtercr.py"
  
  sending [                                             ] 0/3
  sending [                                             ] 0/3
                                                              
                                                              
  sending [==============>                              ] 1/3
  sending [==============>                              ] 1/3
                                                              
                                                              
  sending [=============================>               ] 2/3
  sending [=============================>               ] 2/3
  
  >  -c bar -s test -r tip -b --desc description
  Content-Type: multipart/mixed; boundary="===*" (glob)
  --===* (glob)
  --===* (glob)
  --===*-- (glob)
  $ python -c 'fp = open("utf", "wb"); fp.write("h\xC3\xB6mma!\n"); fp.close();'
  IyBIRyBjaGFuZ2VzZXQgcGF0Y2gKIyBVc2VyIHRlc3QKIyBEYXRlIDQgMAojIE5vZGUgSUQgOTA5
  YTAwZTEzZTlkNzhiNTc1YWVlZTIzZGRkYmFkYTQ2ZDVhMTQzZgojIFBhcmVudCAgZmYyYzlmYTIw
  MThiMTVmYTc0YjMzMzYzYmRhOTUyNzMyM2UyYTk5Zgp1dGYtOCBjb250ZW50CgpkaWZmIC1yIGZm
  MmM5ZmEyMDE4YiAtciA5MDlhMDBlMTNlOWQgZGVzY3JpcHRpb24KLS0tIC9kZXYvbnVsbAlUaHUg
  SmFuIDAxIDAwOjAwOjAwIDE5NzAgKzAwMDAKKysrIGIvZGVzY3JpcHRpb24JVGh1IEphbiAwMSAw
  MDowMDowNCAxOTcwICswMDAwCkBAIC0wLDAgKzEsMyBAQAorYSBtdWx0aWxpbmUKKworZGVzY3Jp
  cHRpb24KZGlmZiAtciBmZjJjOWZhMjAxOGIgLXIgOTA5YTAwZTEzZTlkIHV0ZgotLS0gL2Rldi9u
  dWxsCVRodSBKYW4gMDEgMDA6MDA6MDAgMTk3MCArMDAwMAorKysgYi91dGYJVGh1IEphbiAwMSAw
  MDowMDowNCAxOTcwICswMDAwCkBAIC0wLDAgKzEsMSBAQAoraMO2bW1hIQo=
  $ python -c 'print open("mbox").read().split("\n\n")[1].decode("base64")'
  $ python -c 'fp = open("long", "wb"); fp.write("%s\nfoo\n\nbar\n" % ("x" * 1024)); fp.close();'
  $ python -c 'fp = open("isolatin", "wb"); fp.write("h\xF6mma!\n"); fp.close();'
  $ hg email --date '1970-1-1 0:1' -n -f quux -t foo -c bar -s test -i -r 2
  Content-Type: multipart/mixed; boundary="===*" (glob)
  --===* (glob)
  --===*-- (glob)
  $ hg email --date '1970-1-1 0:1' -n -f quux -t foo -c bar -s test -i -r 4
  Content-Type: multipart/mixed; boundary="===*" (glob)
  --===* (glob)
  --===*-- (glob)
  >  -r 0:1 -r 4
  Content-Type: multipart/mixed; boundary="===*" (glob)
  --===* (glob)
  --===*-- (glob)
  Content-Type: multipart/mixed; boundary="===*" (glob)
  --===* (glob)
  --===*-- (glob)
  Content-Type: multipart/mixed; boundary="===*" (glob)
  --===* (glob)
  --===*-- (glob)
  $ hg email --date '1970-1-1 0:1' -n -f quux -t foo -c bar -s test -a -r 2
  Content-Type: multipart/mixed; boundary="===*" (glob)
  --===* (glob)
  --===* (glob)
  --===*-- (glob)
  $ hg email --date '1970-1-1 0:1' -n -f quux -t foo -c bar -s test -a -r 4
  Content-Type: multipart/mixed; boundary="===*" (glob)
  --===* (glob)
  --===* (glob)
  --===*-- (glob)
  $ hg email --date '1970-1-1 0:1' -n -f quux -t foo -c bar -s test -a --body -r 2
  Content-Type: multipart/mixed; boundary="===*" (glob)
  --===* (glob)
  --===* (glob)
  --===*-- (glob)
  >  -r 0:1 -r 4
  Content-Type: multipart/mixed; boundary="===*" (glob)
  --===* (glob)
  --===* (glob)
  --===*-- (glob)
  Content-Type: multipart/mixed; boundary="===*" (glob)
  --===* (glob)
  --===* (glob)
  --===*-- (glob)
  Content-Type: multipart/mixed; boundary="===*" (glob)
  --===* (glob)
  --===* (glob)
  --===*-- (glob)
  $ hg email --date '1970-1-1 0:1' -n -f quux -t foo -c bar -s test -i -r 2
  Content-Type: multipart/mixed; boundary="===*" (glob)
  --===* (glob)
  --===*-- (glob)
  $ hg email --date '1970-1-1 0:1' -n -f quux -t foo -c bar -s test -i -r 0:1
  Content-Type: multipart/mixed; boundary="===*" (glob)
  --===* (glob)
  --===*-- (glob)
  Content-Type: multipart/mixed; boundary="===*" (glob)
  --===* (glob)
  --===*-- (glob)
  In-Reply-To: <8580ff50825a50c8f716.60@*> (glob)
  References: <8580ff50825a50c8f716.60@*> (glob)
test single flag for single patch:
  >  -r 2
test single flag for multiple patches:
test mutiple flags for single patch:
  $ UUML=`python -c 'import sys; sys.stdout.write("\374")'`
  $ hg --config extensions.graphlog= glog --template "{rev}:{node|short} {desc|firstline}\n"
  $ cd ..