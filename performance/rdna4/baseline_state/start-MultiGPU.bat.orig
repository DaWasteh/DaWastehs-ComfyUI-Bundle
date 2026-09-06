@echo off
chcp 65001 >nul
set "PYTHONUTF8=1"
cd /d "%~dp0"
title ComfyUI Dual GPU - R9700 + RX 9070 XT

echo Starting ComfyUI with both AMD GPUs on port 8188...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-MultiGPU.ps1"
set "EXITCODE=%ERRORLEVEL%"

echo.
echo PowerShell script stopped. ExitCode: %EXITCODE%
echo Press any key to close this window...
pause >nul
exit /b %EXITCODE%
