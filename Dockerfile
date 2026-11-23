FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .

RUN apt-get update && apt-get install -y --no-install-recommends chromium fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY backend ./backend
COPY frontend/src/google-analysis/reportImage.js ./frontend/src/google-analysis/reportImage.js
COPY frontend/src/google-analysis/fonts ./frontend/src/google-analysis/fonts

ENV REPORT_CHROMIUM_PATH=/usr/bin/chromium

EXPOSE 10000

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
