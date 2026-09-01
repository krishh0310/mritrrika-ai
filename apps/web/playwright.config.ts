import { defineConfig, devices } from "@playwright/test";

/**
 * §73 — the full-lifecycle browser test.
 *
 * Deliberately NOT starting its own servers. The lifecycle test drives real
 * OCR against a real database; a `webServer` block that boots and tears those
 * down per run would make the suite both slow and misleading about what it
 * proved. Start the stack first:
 *
 *     docker compose up -d
 *     .venv/bin/python -m uvicorn app.main:app --app-dir apps/api --port 8000
 *     npm run dev
 */
export default defineConfig({
  testDir: "../../tests/e2e",
  // Uploads reference paths relative to the repo root.
  
  timeout: 180_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,        // the lifecycle test is inherently sequential
  workers: 1,
  retries: 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
