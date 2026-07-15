@echo off
chcp 65001 >nul 2>&1
setlocal EnableExtensions

rem TongLing Web standalone launcher (TONGLING_ROOT = this folder)

cd /d "%~dp0"
set "ROOT=%~dp0"
set "TONGLING_ROOT=%ROOT%"

if not exist "%ROOT%tongling_hexstrike_launcher.py" (
  echo [ERROR] Missing tongling_hexstrike_launcher.py. Re-run sync: 独立Web.cmd at project root.
  exit /b 1
)
if not exist "%ROOT%tongling_web" (
  echo [ERROR] Missing tongling_web
  exit /b 1
)

set "PY="
where python >nul 2>&1
if not errorlevel 1 set "PY=python"
if not defined PY if exist "%ROOT%storage\Python311\python.exe" set "PY=%ROOT%storage\Python311\python.exe"
if not defined PY (
  echo [ERROR] Python 3.10+ required
  exit /b 1
)

"%PY%" -c "import flask" >nul 2>&1
if errorlevel 1 call "%~dp0install-deps.cmd"

if not defined HEXSTRIKE_PORT set "HEXSTRIKE_PORT=15038"
if not defined HEXSTRIKE_HOST set "HEXSTRIKE_HOST=0.0.0.0"

echo.
echo TongLing Web standalone - %HEXSTRIKE_HOST%:%HEXSTRIKE_PORT%
echo.

cd /d "%ROOT%"
"%PY%" "%ROOT%tongling_hexstrike_launcher.py" --host %HEXSTRIKE_HOST% --port %HEXSTRIKE_PORT% %*
endlocal
exit /b %ERRORLEVEL%
