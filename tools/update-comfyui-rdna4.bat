@echo off
chcp 65001 >nul
set "PYTHONUTF8=1"
cd /d "%~dp0"
title ComfyUI RDNA4 Update

echo Starte ComfyUI RDNA4 Update...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0update-comfyui-rdna4.ps1"
set "EXITCODE=%ERRORLEVEL%"

echo.
echo Update-Skript beendet. ExitCode: %EXITCODE%
echo Fenster schliessen mit beliebiger Taste...
pause >nul
exit /b %EXITCODE%
