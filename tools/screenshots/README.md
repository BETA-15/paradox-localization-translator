# Screenshots

Taken from the app running in an isolated HOME with a made-up sample mod — never from real user data.

```
D=/Users/Shared/PLT_Demo
python3 make_sample.py $D
mkdir -p $D/src && git -C <repo> archive <tag> app | tar -x -C $D/src   # a copy, so no data beside the repo is picked up
swiftc -O win.swift -o win                   # finds the app window id for screencapture
HOME=$D <repo>/.venv-build/bin/python -I shoot.py $D/src/app $OUT   # .venv-build has tkinterdnd2
rm -rf $D
```

`shoot.py` turns off the scan of external volumes, answers every model list with made-up names
(the author's real models must not appear), hides the version number, then drives the tabs on a timer and saves
translate / model / survey / qa as PNG into `$OUT`.
Copy them to `assets/shots/<lang>/` (or `assets/shots/` for the shared English ones) and run `build.py`.
