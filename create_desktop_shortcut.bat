@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_desktop_shortcut.ps1"
if errorlevel 1 (
    echo Could not create the shortcut.
    pause
)