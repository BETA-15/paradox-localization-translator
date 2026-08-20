#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" - <<'PY'
import sys
try:
    import tkinter
except Exception as e:
    raise SystemExit(f"Tkinter が利用できる Python が必要です: {e}")
print("Python:", sys.version)
print("Tk:", tkinter.TkVersion)
PY

"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install -r requirements-build.txt
rm -rf build dist
"$PYTHON_BIN" -m PyInstaller \
  --noconfirm --clean --windowed --onedir \
  --name "Paradox Localization Translator" \
  --paths app \
  --hidden-import tkinter \
  --hidden-import tkinter.ttk \
  --hidden-import tkinter.filedialog \
  --hidden-import tkinter.messagebox \
  app/main.py

APP="dist/Paradox Localization Translator.app"
if [[ ! -d "$APP" ]]; then
  echo "ERROR: $APP が生成されませんでした" >&2
  exit 1
fi
# Developer IDがなくてもローカル配布しやすいようadhoc署名
codesign --force --deep --sign - "$APP" || true

echo
echo "完成: $APP"
echo "Python/Tk/翻訳コアはアプリ内に内蔵されています。利用者側に必要なのはOllamaとLLMモデルだけです。"
