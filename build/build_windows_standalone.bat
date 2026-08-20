@echo off
setlocal
cd /d "%~dp0\.."

py -3 -c "import sys, tkinter; print('Python:', sys.version); print('Tk:', tkinter.TkVersion)" || exit /b 1
py -3 -m pip install --upgrade pip || exit /b 1
py -3 -m pip install -r requirements-build.txt || exit /b 1

REM Do not delete the source build\ directory: this batch file is running from there.
if exist pyinstaller-build rmdir /s /q pyinstaller-build
if exist dist rmdir /s /q dist

py -3 -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --onefile ^
  --name "ParadoxLocalizationTranslator" ^
  --additional-hooks-dir=. ^
  --paths app ^
  --collect-all tkinterdnd2 ^
  --hidden-import tkinter ^
  --hidden-import tkinter.ttk ^
  --hidden-import tkinter.filedialog ^
  --hidden-import tkinter.messagebox ^
  --hidden-import tkinter.simpledialog ^
  --workpath pyinstaller-build\work ^
  --specpath pyinstaller-build\spec ^
  app\main.py || exit /b 1

echo.
echo Built: dist\ParadoxLocalizationTranslator.exe
echo Python/Tk/translator core are bundled in the EXE. End users only need Ollama and an LLM model.
endlocal
