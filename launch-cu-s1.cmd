@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo CU S1 needs its local environment. Run setup-cu-s1.cmd first.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m cu_s1.app
