@echo off
chcp 65001 >nul
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
if errorlevel 1 (
  echo Sierra 未启动。请查看上方的消息和 data\server.err.log。
  pause
  exit /b 1
)
echo 请在浏览器中打开 http://127.0.0.1:8765/。
pause
endlocal
