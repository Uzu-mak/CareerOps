@echo off
echo Running CareerOps validation in the application image...
docker compose run --rm app python -m compileall -q careerops tests
if errorlevel 1 exit /b 1
docker compose run --rm app pytest -q
if errorlevel 1 exit /b 1
echo.
echo Checking running API (start docker compose first if this fails)...
curl -f http://localhost:8001/api/health
echo.
echo Validation complete.
