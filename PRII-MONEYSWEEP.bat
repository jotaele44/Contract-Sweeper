@echo off
rem Double-click launcher (Windows). First run installs dependencies (needs
rem internet once); later runs start the app directly and work offline.
cd /d "%~dp0"

set "PYTHON="
where py >nul 2>nul && set "PYTHON=py -3"
if not defined PYTHON where python >nul 2>nul && set "PYTHON=python"
if not defined PYTHON (
  echo Python 3 is required. Install it from https://www.python.org/downloads/
  pause
  exit /b 1
)

%PYTHON% desktop\setup.py --ensure
if errorlevel 1 (
  pause
  exit /b 1
)
".venv\Scripts\python.exe" desktop\launch.py %*
if errorlevel 1 pause
