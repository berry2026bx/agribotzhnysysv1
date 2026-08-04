@echo off
setlocal
if "%~1"=="" (
  echo Usage: start_dayuwriter_yolo.cmd MODEL_PATH CLASS_NAME [SERIAL]
  echo Starts display-only YOLO dashboard. Motion remains unarmed.
  exit /b 2
)
set "model=%~1"
set "className=%~2"
set "serial=%~3"
if "%serial%"=="" set "serial=231122070403"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_dayuwriter_yolo.ps1" -Model "%model%" -ClassName "%className%" -Serial "%serial%"
exit /b %errorlevel%
