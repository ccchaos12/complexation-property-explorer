@echo off
setlocal
cd /d "%~dp0"

echo.
echo Complexation Property Explorer - first-time setup
echo ==================================================

where py >nul 2>&1
if errorlevel 1 (
  echo ERROR: The Python launcher was not found.
  echo Install Python 3.11, 3.12, or 3.13 from https://www.python.org/downloads/windows/
  echo Select "Add python.exe to PATH" during installation, then run this file again.
  goto :error
)

set "PYTHON_TAG="
for %%V in (3.13 3.12 3.11) do (
  if not defined PYTHON_TAG (
    py -%%V -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PYTHON_TAG=%%V"
  )
)

if not defined PYTHON_TAG (
  echo ERROR: Python 3.11, 3.12, or 3.13 is required.
  echo Install a supported version, then run this file again.
  goto :error
)

echo Using Python %PYTHON_TAG%.

if /I "%~1"=="--check" (
  echo Windows setup launcher check passed.
  exit /b 0
)

if not exist "data\raw\SRD 46 SQL.zip" (
  echo.
  echo ERROR: The NIST source archive was not found.
  echo Download "SRD 46 SQL.zip" from:
  echo https://data.nist.gov/od/id/mds2-2154
  echo.
  echo Save it exactly as:
  echo %CD%\data\raw\SRD 46 SQL.zip
  goto :error
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating the local Python environment...
  py -%PYTHON_TAG% -m venv .venv
  if errorlevel 1 goto :error
)

echo Installing application dependencies...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements-lock.txt
if errorlevel 1 goto :error

if not exist "data\generated\NIST_SRD_46_rebuilt.db" (
  echo Converting the NIST SQL archive to SQLite...
  ".venv\Scripts\python.exe" scripts\build_srd46_sqlite.py --source "data\raw\SRD 46 SQL.zip" --output "data\generated\NIST_SRD_46_rebuilt.db" --report "data\reports\srd46_build_report.json"
  if errorlevel 1 goto :error
) else (
  echo The rebuilt NIST SQLite database already exists; skipping that step.
)

if not exist "data\generated\stability_constants_canonical.db" (
  echo Building the canonical read-only database...
  ".venv\Scripts\python.exe" -m ingestion.build_canonical --staging "data\generated\NIST_SRD_46_rebuilt.db" --output "data\generated\stability_constants_canonical.db" --report "data\reports\canonical_build_report.json"
  if errorlevel 1 goto :error
) else (
  echo The canonical database already exists; skipping that step.
)

echo.
echo Setup completed successfully. Starting the app...
call "%~dp0run_windows.bat"
exit /b %errorlevel%

:error
echo.
echo Setup did not complete. Read the message above, then try again.
if defined CI exit /b 1
pause
exit /b 1
