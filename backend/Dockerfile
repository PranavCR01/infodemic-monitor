FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/ ./backend/

RUN pip install --no-cache-dir -e ./backend

COPY .env.example .env.example

# CMD is overridden by railway.toml per-service — this is the fallback only
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
