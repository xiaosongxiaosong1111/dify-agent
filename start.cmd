@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
if errorlevel 1 (
  echo Sierra did not start. Review the message above and data\server.err.log.
  pause
  exit /b 1
)
echo Open http://127.0.0.1:8765/ in your browser.
pause
endlocal
