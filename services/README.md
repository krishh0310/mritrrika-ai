# services

Long-running backend processes other than the API.

- `ai-worker/`: Celery worker running the OCR and extraction pipeline. Its heavy ML dependencies are in `ai-worker/requirements.txt`.

Offline libraries that never run as a process belong in `packages/`.
