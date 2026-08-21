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
  --noconfirm --clean --windowed --onedir \
  --name "Paradox Localization Translator" \
  --additional-hooks-dir=. \
  --paths app \
  --collect-all tkinterdnd2 \
  --hidden-import tkinter --hidden-import tkinter.ttk \
  --hidden-import tkinter.filedialog --hidden-import tkinter.messagebox \
  --hidden-import tkinter.simpledialog \
  --workpath pyinstaller-build/work --specpath pyinstaller-build/spec \
  app/main.py
APP="dist/Paradox Localization Translator.app"
[[ -d "$APP" ]] || { echo "ERROR: $APP が生成されませんでした" >&2; exit 1; }
APP_VERSION="$(tr -d '[:space:]' < VERSION)"
PLIST="$APP/Contents/Info.plist"
if [[ -f "$PLIST" ]]; then
  /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $APP_VERSION" "$PLIST" 2>/dev/null || /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $APP_VERSION" "$PLIST"
  /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $APP_VERSION" "$PLIST" 2>/dev/null || /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $APP_VERSION" "$PLIST"
  /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier com.beta15.ParadoxLocalizationTranslator" "$PLIST" 2>/dev/null || /usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string com.beta15.ParadoxLocalizationTranslator" "$PLIST"
fi
codesign --force --deep --sign - "$APP" || true
echo "完成: $APP"
