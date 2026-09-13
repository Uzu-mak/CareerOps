FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends chromium fonts-dejavu-core libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV CHROMIUM_EXECUTABLE=/usr/bin/chromium
CMD ["uvicorn","careerops.main:app","--host","0.0.0.0","--port","8000"]
