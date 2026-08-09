@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm VoiceGun.spec
if errorlevel 1 (
    echo.
    echo Build failed. See the messages above.
    pause
    exit /b 1
)

copy /Y "LICENSE" "dist\VoiceGun\LICENSE" >nul
copy /Y "README.md" "dist\VoiceGun\README.md" >nul

echo.
echo Build completed: dist\VoiceGun\VoiceGun.exe
echo Run package_windows.bat separately when a ZIP archive is required.
exit /b 0
