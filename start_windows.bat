@echo off
setlocal
cd /d "%~dp0"

if /I "%~1"=="--check" (
  call "%~dp0setup_windows.bat" --check
  if errorlevel 1 goto :error
  call "%~dp0run_windows.bat" --check
  if errorlevel 1 goto :error
  echo One-click Windows launcher check passed.
  exit /b 0
)

echo.
echo Complexation Property Explorer - one-click start
echo =================================================
echo The first start downloads the official NIST package, builds the local
echo databases, and installs Python dependencies. This can take several minutes.
echo.

call "%~dp0setup_windows.bat" --prepare-only
if errorlevel 1 goto :error

call "%~dp0run_windows.bat"
exit /b %errorlevel%

:error
echo.
echo The application did not start. Read the message above, then try again.
if defined CI exit /b 1
pause
exit /b 1
