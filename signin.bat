@echo off
REM Sign in to a job site once so CareerOps can apply there. Usage: signin.bat "https://site/login"
cd /d "%~dp0"
if "%~1"=="" (
  echo Usage: signin.bat "https://www.example.com/login"
  exit /b 1
)
set PY=python
where py >nul 2>&1 && set PY=py
%PY% -c "import playwright" 2>nul
if errorlevel 1 (
  echo Installing Playwright for the sign-in window ^(one time^)...
  %PY% -m pip install --user --quiet playwright
  if errorlevel 1 exit /b 1
)
%PY% scripts\signin.py %*
