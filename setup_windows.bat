@echo off
setlocal
cd /d "%~dp0"

echo.
echo Complexation Property Explorer - first-time setup
echo ==================================================

set "PYTHON_LAUNCHER="
where py >nul 2>&1
if not errorlevel 1 set "PYTHON_LAUNCHER=py"
if not defined PYTHON_LAUNCHER (
  where python >nul 2>&1
  if not errorlevel 1 set "PYTHON_LAUNCHER=python"
)

if not defined PYTHON_LAUNCHER (
  echo ERROR: Python was not found.
  echo Install Python 3.11, 3.12, or 3.13 from https://www.python.org/downloads/windows/
  echo Select "Add python.exe to PATH" during installation, then run this file again.
  start "" "https://www.python.org/downloads/windows/"
  goto :error
)

set "PYTHON_TAG="
if /I "%PYTHON_LAUNCHER%"=="py" (
  for %%V in (3.13 3.12 3.11) do (
    if not defined PYTHON_TAG (
      py -%%V -c "import sys" >nul 2>&1
      if not errorlevel 1 set "PYTHON_TAG=%%V"
    )
  )
) else (
  python -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info < (3, 14) else 1)" >nul 2>&1
  if not errorlevel 1 set "PYTHON_TAG=PATH"
)

if not defined PYTHON_TAG (
  echo ERROR: Python 3.11, 3.12, or 3.13 is required.
  echo Install a supported version, then run this file again.
  start "" "https://www.python.org/downloads/windows/"
  goto :error
)

echo Using supported Python from %PYTHON_LAUNCHER%.

if /I "%~1"=="--check" (
  echo Windows setup launcher check passed.
  exit /b 0
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating the local Python environment...
  if /I "%PYTHON_LAUNCHER%"=="py" (
    py -%PYTHON_TAG% -m venv .venv
  ) else (
    python -m venv .venv
  )
  if errorlevel 1 goto :error
)

echo Installing application dependencies...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements-lock.txt
if errorlevel 1 goto :error

echo Preparing the official NIST source and local databases...
".venv\Scripts\python.exe" -m scripts.prepare_app
if errorlevel 1 goto :error

if /I "%~1"=="--prepare-only" (
  echo Setup preparation completed successfully.
  exit /b 0
)

echo.
echo Setup completed successfully. Starting the app...
call "%~dp0run_windows.bat"
exit /b %errorlevel%

:error
echo.
echo Setup did not complete. Check the internet connection and read the message above.
if defined CI exit /b 1
pause
exit /b 1
