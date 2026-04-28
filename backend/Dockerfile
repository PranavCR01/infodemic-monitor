FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# ML_DEPS=true adds libgl1/libglib2/libgomp (needed by EasyOCR / faster-whisper).
# Keep false on Railway — WHISPER_PROVIDER=openai and OCR is disabled there.
ARG ML_DEPS=false

RUN apt-get update \
  && apt-get install -y --no-install-recommends ffmpeg \
  && if [ "$ML_DEPS" = "true" ]; then \
       apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1; \
     fi \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/ ./backend/

RUN if [ "$ML_DEPS" = "true" ]; then \
      pip install --no-cache-dir -e "./backend[ml]"; \
    else \
      pip install --no-cache-dir -e "./backend"; \
    fi

COPY .env.example .env.example

# CMD is overridden by railway.toml per-service — this is the fallback only
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
