import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

/**
 * Two things that looked finished and were not:
 *
 *   §35  The tehsildar assistant. Officers own no land, and the assistant
 *        only knew ownership scope, so every officer question came back
 *        "no land records are linked to your account". There was no screen.
 *   §21  PDF uploads. The allowlist accepted them; nothing rendered them, so
 *        every PDF was recorded as a failed quality check.
 *
 * Requires the stack up (see playwright.config.ts).
 */

const REPO_ROOT = path.resolve(__dirname, "../..");
const API = process.env.E2E_API_URL ?? "http://localhost:8000";
const PASSWORD = process.env.DEMO_PASSWORD ?? "demo_change_me";

async function signIn(page: Page, email: string) {
  // Sign whoever is already here out first: /login redirects a signed-in user
  // to their dashboard, so switching roles mid-test found no login form.
  // sessionStorage is where the tokens live, so clearing it IS signing out.
  await page.goto("/login");
  await page.evaluate(() => window.sessionStorage.clear());
  await page.goto("/login");
  await page.fill('input[name="email"]', email);
  await page.fill('input[name="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/(citizen|deo|verifier|tehsildar)\//);
}

/** A generated dataset file, by repo-relative path. */
function fixture(relative: string): string {
  return path.join(REPO_ROOT, relative);
}

/** Bind two clean Khasra scans from the generated dataset into one PDF. */
function twoPagePdf(): string {
  const out = path.join(REPO_ROOT, "apps/web/test-results/e2e-two-page.pdf");
  fs.mkdirSync(path.dirname(out), { recursive: true });
  execFileSync(
    path.join(REPO_ROOT, ".venv/bin/python"),
    [
      "-c",
      [
        "import json, sys",
        "from PIL import Image",
        "root, out = sys.argv[1], sys.argv[2]",
        "docs = json.load(open(root + '/datasets/metadata/documents.v1.json'))",
        "clean = [d for d in docs if d['difficulty'] == 'clean' and d['template'] == 'KHASRA_A'][:2]",
        "pages = [Image.open(root + '/datasets/' + d['degraded_image']).convert('RGB') for d in clean]",
        "pages[0].save(out, 'PDF', save_all=True, append_images=pages[1:], resolution=150)",
      ].join("\n"),
      REPO_ROOT,
      out,
    ],
  );
  return out;
}

test.describe("the tehsildar assistant (§35)", () => {
  test("answers from records in the officer's jurisdiction, with citations", async ({
    page,
  }) => {
    await signIn(page, "tehsildar@mrittika.demo");

    // Reachable from the tehsildar's own navigation, not only by URL.
    await page.getByRole("link", { name: "Assistant" }).click();
    await page.waitForURL(/\/tehsildar\/assistant$/);

    await page
      .getByRole("button", { name: "Which mutation transferred ownership of khasra 142/2?" })
      .click();

    await expect(page.getByText("PARCEL-UP-DEMO-0142").first()).toBeVisible({
      timeout: 60_000,
    });
    await expect(page.getByText(/no land records are linked/i)).toHaveCount(0);
  });
});

test.describe("a multi-page PDF (§21, §28)", () => {
  test.describe.configure({ mode: "serial" });

  let documentId: string;

  test("a DEO uploads a PDF and it passes the quality gate as pages", async ({ page }) => {
    await signIn(page, "deo@mrittika.demo");
    await page.goto("/deo/upload");

    await page.setInputFiles('input[type="file"]', twoPagePdf());
    await page.selectOption('select:near(:text("Document type"))', "KHASRA");
    await page.getByRole("combobox", { name: "Village" }).selectOption({ label: "रामपुर" });
    await page.getByRole("button", { name: /upload and check quality/i }).click();

    await page.waitForURL(/\/deo\/documents\/DOC-\d+/);
    documentId = page.url().split("/").pop()!;

    await expect(page.getByText(/scan quality/i)).toBeVisible();
    await expect(page.getByText(/could not decode/i)).toHaveCount(0);

    await page.getByRole("button", { name: /start processing/i }).click();
    await expect(page.getByText(/awaiting verification/i)).toBeVisible({
      timeout: 170_000,
    });
  });

  test("the verifier moves between pages, and a field opens its own page", async ({
    page,
    request,
  }) => {
    // Find a page-1 field from the API, so the assertion does not depend on
    // what OCR happened to read.
    const login = await request.post(`${API}/api/v1/auth/login`, {
      data: { email: "lekhpal@mrittika.demo", password: PASSWORD },
    });
    const { access_token } = await login.json();
    const workspace = await (
      await request.get(`${API}/api/v1/verifications/${documentId}/workspace`, {
        headers: { Authorization: `Bearer ${access_token}` },
      })
    ).json();
    expect(workspace.pages.map((p: { page_number: number }) => p.page_number)).toEqual([1, 2]);
    const pageOneField = workspace.fields.find(
      (f: { page_number: number; field: string; normalized_value: string | null }) =>
        f.page_number === 1 && f.field === "KHASRA" && f.normalized_value,
    );
    expect(pageOneField, "OCR found no KHASRA on page 1").toBeTruthy();

    await signIn(page, "lekhpal@mrittika.demo");
    await page.goto(`/verifier/documents/${documentId}`);

    const pages = page.getByRole("navigation", { name: "Document pages" });
    await expect(pages).toContainText("Page 1 of 2");

    await pages.getByRole("button", { name: "Next page" }).click();
    await expect(pages).toContainText("Page 2 of 2");

    // Selecting a field that lives on page 1 brings page 1 back.
    await page.getByText(pageOneField.normalized_value, { exact: true }).first().click();
    await expect(pages).toContainText("Page 1 of 2");
  });
});

test.describe("reading records in English (§14, §28)", () => {
  test("the verifier can switch languages, and the Hindi stays visible", async ({ page }) => {
    await signIn(page, "lekhpal@mrittika.demo");
    await page.goto("/verifier/queue");

    const firstDocument = page.locator('a[href^="/verifier/documents/DOC-"]').first();
    await expect(firstDocument).toBeVisible();
    await firstDocument.click();
    await page.waitForURL(/\/verifier\/documents\/DOC-\d+/);
    await expect(page.getByRole("heading", { name: /extracted fields/i })).toBeVisible();

    const toggle = page.getByRole("group", { name: "Show record values in" });
    await toggle.getByRole("button", { name: "English" }).click();

    // A land classification reads in English, with the Hindi beside it.
    const irrigated = page.getByText("Irrigated", { exact: true }).first();
    await expect(irrigated).toBeVisible();
    await expect(page.getByText("सिंचित", { exact: true }).first()).toBeVisible();

    // And the choice is honoured the other way.
    await toggle.getByRole("button", { name: "हिन्दी" }).click();
    await expect(page.getByText("Irrigated", { exact: true })).toHaveCount(0);
    await expect(page.getByText("सिंचित", { exact: true }).first()).toBeVisible();
  });

  test("a citizen sees English place names from the records, not guesses", async ({ page }) => {
    await signIn(page, "seema32@mrittika.demo");
    await page.goto("/citizen/my-land");

    await page
      .getByRole("group", { name: "Show record values in" })
      .getByRole("button", { name: "English" })
      .click();

    // रामपुर is an official name in the locations table, so it must render as
    // the recorded "Rampur" rather than a transliteration of the Devanagari.
    await expect(page.getByText("Rampur", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("रामपुर", { exact: true }).first()).toBeVisible();
  });
});

test.describe("re-running extraction (§29)", () => {
  test("a verifier re-runs an untouched document and sees fresh fields", async ({
    page,
    request,
  }) => {
    await signIn(page, "deo@mrittika.demo");
    await page.goto("/deo/upload");
    await page.setInputFiles('input[type="file"]', fixture("datasets/generated/degraded/DOC-00016.jpg"));
    await page.selectOption('select:near(:text("Document type"))', "KHASRA");
    await page.getByRole("combobox", { name: "Village" }).selectOption({ label: "रामपुर" });
    await page.getByRole("button", { name: /upload and check quality/i }).click();
    await page.waitForURL(/\/deo\/documents\/DOC-\d+/);
    const documentId = page.url().split("/").pop()!;
    await page.getByRole("button", { name: /start processing/i }).click();
    await expect(page.getByText(/awaiting verification/i)).toBeVisible({ timeout: 170_000 });

    await signIn(page, "lekhpal@mrittika.demo");
    await page.goto(`/verifier/documents/${documentId}`);

    await page.getByRole("button", { name: /re-run extraction/i }).click();
    await page.getByRole("alertdialog", { name: /confirm re-running/i })
      .getByRole("button", { name: "Re-run" }).click();

    await expect(page.getByText(/extraction re-run/i)).toBeVisible({ timeout: 170_000 });
    await expect(page.getByRole("heading", { name: /extracted fields/i })).toBeVisible();

    // Once a field carries human work, re-running is no longer offered -- it
    // would discard that work. The refusal itself is covered by the API tests;
    // what matters here is that the control disappears. The correction is made
    // through the API because the field list re-mounts as the re-run's results
    // arrive, which cancels an in-progress edit in the UI.
    const { access_token } = await (
      await request.post(`${API}/api/v1/auth/login`, {
        data: { email: "lekhpal@mrittika.demo", password: PASSWORD },
      })
    ).json();
    const workspace = await (
      await request.get(`${API}/api/v1/verifications/${documentId}/workspace`, {
        headers: { Authorization: `Bearer ${access_token}` },
      })
    ).json();
    const patched = await request.patch(
      `${API}/api/v1/verifications/extractions/${workspace.fields[0].extraction_id}`,
      {
        headers: { Authorization: `Bearer ${access_token}` },
        data: { value: "corrected-by-e2e" },
      },
    );
    expect(patched.ok(), await patched.text()).toBeTruthy();

    await page.reload();
    await expect(page.getByRole("heading", { name: /extracted fields/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /re-run extraction/i })).toHaveCount(0);
  });
});
