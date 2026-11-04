@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-cu-s1.ps1"
if errorlevel 1 (
  echo.
  echo Setup did not finish. Review the error above and README.md.
  pause
  exit /b 1
)
echo.
echo Setup complete. Open launch-cu-s1.cmd to use CU S1.
pause
