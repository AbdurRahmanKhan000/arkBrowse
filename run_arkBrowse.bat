@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0arkbrowse.py"
    exit /b 0
)

where pythonw.exe >nul 2>&1
if not errorlevel 1 (
    start "" pythonw.exe "%~dp0arkbrowse.py"
    exit /b 0
)

echo Python 3.10+ was not found. Install Python and run:
echo   python -m pip install -r requirements.txt
pause