@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo The local Python environment is missing.
  echo Double-click setup_windows.bat first.
  goto :error
)

set "DATABASE_PATH=%COMPLEXATION_DB_PATH%"
if not defined DATABASE_PATH set "DATABASE_PATH=%CD%\data\generated\stability_constants_canonical.db"

if not exist "%DATABASE_PATH%" (
  echo The read-only SQLite database was not found:
  echo %DATABASE_PATH%
  echo Double-click setup_windows.bat to build it.
  goto :error
)

if /I "%~1"=="--check" (
  ".venv\Scripts\python.exe" -c "import streamlit, complexation_explorer"
  if errorlevel 1 goto :error
  echo Windows runtime launcher check passed.
  exit /b 0
)

echo Starting Complexation Property Explorer...
echo Your browser should open at http://localhost:8501
".venv\Scripts\python.exe" -m streamlit run app.py
exit /b %errorlevel%

:error
echo.
if defined CI exit /b 1
pause
exit /b 1
