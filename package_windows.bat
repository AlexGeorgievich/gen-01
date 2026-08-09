@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "tools\package_windows.ps1"
if errorlevel 1 (
    echo.
    echo Packaging failed. See the messages above.
    pause
    exit /b 1
)

echo.
echo Packaging completed.
exit /b 0
