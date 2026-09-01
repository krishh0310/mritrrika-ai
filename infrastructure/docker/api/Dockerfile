# The FastAPI service (§75).
#
# Installs requirements-api.txt only — NOT requirements-ai.txt. The API never
# loads an OCR model; it hands work to the worker. Keeping the AI wheels out
# takes the image from ~2.5GB to ~400MB and makes it start in seconds.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libpq for psycopg, and the GEOS/PROJ pair GeoAlchemy2 needs to parse geometry.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpq5 libgeos-c1v5 libproj25 curl \
    && rm -rf /var/lib/apt/lists/*

# Dependencies in their own layer, so a source edit does not reinstall them.
COPY requirements-api.txt ./
RUN pip install -r requirements-api.txt

COPY packages/domain ./packages/domain
COPY services/ai-worker ./services/ai-worker
COPY apps/api ./apps/api
COPY scripts ./scripts

# Not root. A container that never needs to write to its own filesystem should
# not be able to.
RUN useradd --system --uid 10001 mrittika && chown -R mrittika /app
USER mrittika

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--app-dir", "apps/api", \
     "--host", "0.0.0.0", "--port", "8000"]
