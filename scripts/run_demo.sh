#!/usr/bin/env bash
set -e
export DATABASE_URL=${DATABASE_URL:-sqlite:///./careerops.db}
export BASE_URL=${BASE_URL:-http://127.0.0.1:8000}
export CHROMIUM_EXECUTABLE=${CHROMIUM_EXECUTABLE:-/usr/bin/chromium}
uvicorn careerops.main:app --host 127.0.0.1 --port 8000
