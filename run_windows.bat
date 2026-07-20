@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo The local Python environment is missing.
  echo Double-click start_windows.bat to prepare and start the app.
  goto :error
)

set "DATABASE_PATH=%COMPLEXATION_DB_PATH%"
if not defined DATABASE_PATH set "DATABASE_PATH=%CD%\data\generated\Complexation_Constants_Unified_rebuilt.db"

if not exist "%DATABASE_PATH%" (
  echo The read-only SQLite database was not found:
  echo %DATABASE_PATH%
  echo Double-click start_windows.bat to download and build it.
  goto :error
)

if /I "%~1"=="--check" (
  ".venv\Scripts\python.exe" scripts\launch_app.py --check
  if errorlevel 1 goto :error
  echo Windows runtime launcher check passed.
  exit /b 0
)

echo Starting Complexation Property Explorer...
echo The default browser will open automatically when the app is ready.
".venv\Scripts\python.exe" scripts\launch_app.py
exit /b %errorlevel%

:error
echo.
if defined CI exit /b 1
pause
exit /b 1
