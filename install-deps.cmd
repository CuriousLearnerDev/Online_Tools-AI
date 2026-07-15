@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set "PY="
where python >nul 2>&1
if not errorlevel 1 set "PY=python"
if not defined PY if exist "%~dp0storage\Python311\python.exe" set "PY=%~dp0storage\Python311\python.exe"
if not defined PY (
  echo [ERROR] Python not found
  exit /b 1
)

"%PY%" -m pip install -r "%~dp0requirements-web.txt"
exit /b %ERRORLEVEL%
