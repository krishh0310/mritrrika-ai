# Contributing

Use Python 3.12 and Node.js 20+. Follow the setup in `README.md`; keep generated datasets, model weights, and secrets out of Git. Put business rules in the existing service or domain package, and put permission checks in the API rather than the client. New public functions need docstrings and a focused test that would fail if their behavior broke.

Before a pull request, run `.venv/bin/python -m ruff check .`, `.venv/bin/python -m pytest tests -m 'not slow'`, `npm run lint`, `npm run typecheck`, and `npm test`. Integration and browser tests need the seeded Docker services described in `README.md`. Update `docs/domain-mapping.md` when a declared capability changes, and update benchmark claims only with a fresh run of `benchmarks/benchmark.py`.
