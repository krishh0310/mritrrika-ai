# tests

All tests, grouped by component. Run `pytest tests` for the Python suites and `npm run e2e` for the browser tests.

- `ai/`, `backend/`, `dataset/`: pytest suites (`-m "not slow"` skips model-loading tests)
- `integration/`: needs Postgres, Redis and MinIO running
- `e2e/`: Playwright, configured in `apps/web/playwright.config.ts`
