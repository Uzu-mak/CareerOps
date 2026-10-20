@echo off
REM Start CareerOps (API, PostgreSQL, Watchtower) in the background and open it.
cd /d "%~dp0"
if not exist .env (
  echo No .env file found. Run: copy .env.example .env   then edit it.
  exit /b 1
)
docker version >nul 2>&1
if errorlevel 1 (
  echo Docker Desktop is not running. Start it, wait for "Engine running", then try again.
  exit /b 1
)
echo Starting CareerOps...
docker compose up -d --build
if errorlevel 1 exit /b 1

echo Waiting for CareerOps to answer on http://localhost:8001 ...
for /l %%i in (1,1,60) do (
  curl -s -o nul -f http://localhost:8001/api/health && goto ready
  timeout /t 2 /nobreak >nul
)
echo CareerOps did not start. Recent app log:
docker compose logs app --tail 40
exit /b 1

:ready
echo.
echo   CareerOps is running:  http://localhost:8001
echo   Logs:   docker compose logs -f app
echo   Stop:   stop_careerops.bat
echo.
start "" http://localhost:8001
