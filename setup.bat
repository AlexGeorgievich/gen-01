@echo off
setlocal
cd /d "%~dp0"
py -3 -m venv .venv
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error
echo.
echo Installation completed. Start the program with run.bat
pause
exit /b 0
:error
echo.
echo Installation failed. Check Python 3 and Internet connection.
pause
exit /b 1
