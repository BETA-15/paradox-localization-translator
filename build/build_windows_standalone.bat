@echo off
setlocal
cd /d "%~dp0\.."
py -3 -c "import sys, tkinter; print('Python:', sys.version); print('Tk:', tkinter.TkVersion)" || exit /b 1
py -3 -m pip install --upgrade pip || exit /b 1
py -3 -m pip install -r requirements-build.txt || exit /b 1
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
py -3 -m PyInstaller --noconfirm --clean --windowed --onefile --name "ParadoxLocalizationTranslator" --paths app --hidden-import tkinter --hidden-import tkinter.ttk --hidden-import tkinter.filedialog --hidden-import tkinter.messagebox app\main.py || exit /b 1
echo.
echo 完成: dist\ParadoxLocalizationTranslator.exe
echo Python/Tk/翻訳コアはEXE内に内蔵されています。利用者側に必要なのはOllamaとLLMモデルだけです。
endlocal
