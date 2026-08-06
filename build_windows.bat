@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm GPT01.spec
if errorlevel 1 (
    echo.
    echo Build failed. See the messages above.
    pause
    exit /b 1
)

copy /Y "LICENSE" "dist\GPT01\LICENSE" >nul
copy /Y "README.md" "dist\GPT01\README.md" >nul

echo.
echo Build completed: dist\GPT01\GPT01.exe
exit /b 0
