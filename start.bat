@echo off
cd /d "%~dp0"
python -c "print('Python OK')" 2>&1
if errorlevel 1 (
    echo Python not found!
    pause
    exit /b 1
)
python -c "import pymupdf; print('pymupdf OK')" 2>&1
python -c "import yaml; print('yaml OK')" 2>&1
python -c "import pywinauto; print('pywinauto OK')" 2>&1
python -c "import pyautogui; print('pyautogui OK')" 2>&1
python -c "import pyperclip; print('pyperclip OK')" 2>&1
python -c "from gui.app import MainApp; print('gui OK')" 2>&1
echo.
echo Starting app...
python start.py 2>&1
echo.
echo === Exited ===
pause
