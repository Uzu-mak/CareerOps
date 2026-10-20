@echo off
REM Fill a CareerOps application in your own browser; you click Submit. Usage: finish.bat 433
cd /d "%~dp0"
if "%~1"=="" (
  echo Usage: finish.bat JOB_NUMBER   ^(the number in localhost:8001/jobs/NUMBER^)
  exit /b 1
)
set PY=python
where py >nul 2>&1 && set PY=py
%PY% -c "import playwright" 2>nul
if errorlevel 1 (
  echo Installing Playwright for the browser window ^(one time^)...
  %PY% -m pip install --user --quiet playwright
  if errorlevel 1 exit /b 1
)
%PY% scripts\finish.py %*
