@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0start_dayuwriter_gui.ps1"
exit /b %errorlevel%
