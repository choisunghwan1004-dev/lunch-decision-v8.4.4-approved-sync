@echo off
rem Find an installed Python without requiring the optional py launcher.
cd /d "%~dp0.."
if exist .venv\Scripts\python.exe goto existing
where python >nul 2>nul
if errorlevel 1 goto try_py
python -c "import sys;sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
if errorlevel 1 goto try_py
python -m venv .venv
if errorlevel 1 exit /b 1
goto existing
:try_py
where py >nul 2>nul
if errorlevel 1 goto missing
py -3 -c "import sys;sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
if errorlevel 1 goto missing
py -3 -m venv .venv
if errorlevel 1 exit /b 1
:existing
.venv\Scripts\python.exe -c "import sys;sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
if errorlevel 1 goto missing
exit /b 0
:missing
echo Python 3.11 or newer is required. Install Python and reopen PowerShell.
echo Check: python --version
exit /b 1
