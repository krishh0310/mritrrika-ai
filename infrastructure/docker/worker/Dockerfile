# The Celery AI worker (§75).
#
# This one DOES carry the heavy stack, which is the whole reason it is a
# separate image from the API: OCR and layout models must not be loaded into
# an HTTP worker process (§84).
#
# NOTE on architecture: paddlepaddle publishes no reliable linux/arm64 wheel.
# Build and run this image on x86_64. On Apple Silicon, run the worker
# natively instead — see docs/architecture.md "Runtime topology".

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # Where PaddleOCR caches downloaded weights; mounted as a volume so a
    # restart does not re-download them.
    PADDLE_HOME=/app/models/paddle

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      libpq5 libgeos-c1v5 libproj25 \
      libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
      libraqm0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-api.txt requirements-ai.txt ./
RUN pip install -r requirements-api.txt -r requirements-ai.txt

COPY packages/domain ./packages/domain
COPY services ./services
COPY apps/api ./apps/api

RUN useradd --system --uid 10001 mrittika \
    && mkdir -p /app/models/paddle && chown -R mrittika /app
USER mrittika
WORKDIR /app/apps/api

# --concurrency=1: each worker caches a model, and two copies of PaddleOCR in
# one container is the fastest way to exhaust memory. Scale with replicas.
CMD ["celery", "-A", "app.worker.celery_app", "worker", \
     "--loglevel=info", "--concurrency=1"]
