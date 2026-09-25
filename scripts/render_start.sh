#!/bin/sh
# Render free web services have no pre-deploy step: migrate, then serve.
set -e
python -m alembic -c apps/api/alembic.ini upgrade head
exec uvicorn app.main:app --app-dir apps/api --host 0.0.0.0 --port "${PORT:-8000}"
