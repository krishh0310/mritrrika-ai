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
  await page.goto("/login");
  await page.fill('input[name="email"]', email);
  await page.fill('input[name="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/(citizen|deo|verifier|tehsildar)\//);
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
