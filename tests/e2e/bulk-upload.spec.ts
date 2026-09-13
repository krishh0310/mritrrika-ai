import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

/**
 * §21 — a DEO uploads a tray of scans.
 *
 * The backend tests cover the batching rules. What only a browser can show is
 * the part that matters to the operator: partial success renders as TWO lists,
 * so a tray containing one duplicate still reports the files that landed and
 * names the document the rejected one duplicates.
 *
 * Requires the stack up (see playwright.config.ts).
 */

const REPO_ROOT = path.resolve(__dirname, "../..");
const PASSWORD = process.env.DEMO_PASSWORD ?? "demo_change_me";
const DEO = "deo@mrittika.demo";

async function signIn(page: Page, email: string) {
  await page.goto("/login");
  await page.evaluate(() => window.sessionStorage.clear());
  await page.goto("/login");
  await page.fill('input[name="email"]', email);
  await page.fill('input[name="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/(citizen|deo|verifier|tehsildar)\//);
}

/**
 * A corpus page made unique for this run.
 *
 * The demo database is seeded from the same corpus, so a page straight off
 * disk is already stored and would be rejected as a duplicate before the test
 * reaches its point. A few bytes appended after the JPEG's end-of-image marker
 * change the file without changing the image.
 */
function uniqueScan(sourceRelative: string, tag: string): string {
  const source = path.join(REPO_ROOT, sourceRelative);
  const bytes = Buffer.concat([
    fs.readFileSync(source),
    Buffer.from(`\n<!-- ${tag} ${Date.now()} ${Math.random()} -->`),
  ]);
  const out = path.join(os.tmpdir(), `mrittika-batch-${tag}-${Date.now()}.jpg`);
  fs.writeFileSync(out, bytes);
  return out;
}

test.describe("batch upload (§21)", () => {
  test("a tray with a duplicate still stores the rest, and says why", async ({ page }) => {
    const indexPath = path.join(REPO_ROOT, "datasets/metadata/documents.v1.json");
    test.skip(!fs.existsSync(indexPath), "run scripts/generate_documents.py first");

    const index = JSON.parse(fs.readFileSync(indexPath, "utf8"));
    const clean = index.filter((d: { difficulty: string }) => d.difficulty === "clean");
    test.skip(clean.length < 2, "need two clean pages in the corpus");

    const first = uniqueScan(`datasets/${clean[0].degraded_image}`, "a");
    const second = uniqueScan(`datasets/${clean[1].degraded_image}`, "b");

    await signIn(page, DEO);
    await page.goto("/deo/bulk");

    // The same file twice, plus a different one: the ordinary scanning slip.
    await page.getByLabel("Scans").setInputFiles([first, first, second]);
    await page.getByLabel("Village").selectOption({ index: 1 });
    await page.getByRole("button", { name: /Upload \d+ scans?/ }).click();

    await expect(page.getByRole("heading", { name: "Result" })).toBeVisible({
      timeout: 60_000,
    });
    // exact: true, or "Stored" also matches "Not stored".
    await expect(
      page.getByRole("heading", { name: "Stored", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Not stored", exact: true }),
    ).toBeVisible();

    // The rejection names the document that already holds those bytes --
    // without it an operator uploads a renamed copy instead.
    await expect(
      page.getByRole("link", { name: /^DOC-\d+$/ }).first(),
    ).toBeVisible();
  });

  test("the batch screen asks only for what is true of the whole tray", async ({ page }) => {
    // Khasra and khata differ per page, so asking for them here would invite
    // one number being applied to forty documents.
    await signIn(page, DEO);
    await page.goto("/deo/bulk");

    await expect(page.getByLabel("Village")).toBeVisible();
    await expect(page.getByLabel("Document type")).toBeVisible();
    await expect(page.getByLabel("Khasra number")).toHaveCount(0);
    await expect(page.getByLabel("Khata number")).toHaveCount(0);
  });
});
