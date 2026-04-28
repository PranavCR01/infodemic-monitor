FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
  && apt-get install -y --no-install-recommends ffmpeg \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install base deps from requirements.txt first — no ML packages, no egg-info ambiguity.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r ./backend/requirements.txt

# Copy source and register the package for import (--no-deps: deps already installed above).
COPY backend/ ./backend/
RUN pip install --no-cache-dir --no-deps -e ./backend

COPY .env.example .env.example

# CMD is overridden by railway.toml per-service — this is the fallback only
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
