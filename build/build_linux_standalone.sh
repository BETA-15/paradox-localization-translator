#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" - <<'PY'
import sys, tkinter
print("Python:", sys.version)
print("Tk:", tkinter.TkVersion)
PY
"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install -r requirements-build.txt
rm -rf pyinstaller-build dist
"$PYTHON_BIN" -m PyInstaller \
  --noconfirm --clean --windowed --onefile \
  --name "ParadoxLocalizationTranslator" \
  --paths app \
  --collect-all tkinterdnd2 \
  --hidden-import tkinter --hidden-import tkinter.ttk \
  --hidden-import tkinter.filedialog --hidden-import tkinter.messagebox \
  --hidden-import tkinter.simpledialog \
  --workpath pyinstaller-build/work --specpath pyinstaller-build/spec \
  app/main.py
echo "完成: dist/ParadoxLocalizationTranslator"
