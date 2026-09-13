@echo off
set BASE=http://localhost:8001
echo CareerOps v3.0 source network is seeded automatically.
echo Forcing an immediate scan of all enabled sources and the job-alert inbox...
curl -s -X POST "%BASE%/api/discover/run-configured"
echo.
echo Refresh %BASE%
pause
