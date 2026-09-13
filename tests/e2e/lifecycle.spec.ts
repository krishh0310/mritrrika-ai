import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { freshScan } from "./fresh-scan";

// Playwright resolves relative paths against the cwd it was launched from
// (apps/web), not the repo root, so a bare "datasets/..." path only worked
// when the suite happened to be run from the root. Anchor to this file.
const REPO_ROOT = path.resolve(__dirname, "../..");
const fixture = (rel: string) => path.join(REPO_ROOT, rel);

/**
 * §73 — the whole land-record lifecycle, in one browser test.
 *
 * This is the test §92 calls the definition of done. It follows ONE document
 * and ONE parcel through every hand that touches them:
 *
 *     DEO uploads  →  pipeline extracts  →  verifier corrects and submits
 *       →  tehsildar approves  →  citizen sees the parcel, its map, its
 *          ownership history, asks the assistant, reads the audit trail
 *
 * The point is that the same document_id and parcel_id travel the whole way.
 * Four disconnected screenshots would prove nothing; §91 forbids faking the
 * workflow with independent static pages.
 *
 * Requires the stack up (see playwright.config.ts).
 */

const PASSWORD = process.env.DEMO_PASSWORD ?? "demo_change_me";

const USERS = {
  deo: "deo@mrittika.demo",
  verifier: "lekhpal@mrittika.demo",
  tehsildar: "tehsildar@mrittika.demo",
  citizenA: "ram31@mrittika.demo",
  citizenB: "seema32@mrittika.demo",
};

/**
 * The parcel the uploaded document is linked to, held by citizen A.
 *
 * This must be one of the generator's EXPLICIT demo grants, not just a parcel
 * that happened to fall to citizen A: holdings are assigned from a seeded
 * shuffle, so widening the world re-deals them and a merely-observed parcel
 * silently stops belonging to this citizen. `_grant` pins 0181 to owner A and
 * raises if the parcel ever stops existing.
 */
const PARCEL = "PARCEL-UP-DEMO-0181";

async function signIn(page: Page, email: string) {
  await page.goto("/login");
  await page.fill('input[name="email"]', email);
  await page.fill('input[name="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/(citizen|deo|verifier|tehsildar)\//);
}

async function signOut(page: Page) {
  // sessionStorage is where the tokens live, so clearing it IS signing out.
  await page.evaluate(() => window.sessionStorage.clear());
}

test.describe("the land-record lifecycle", () => {
  // One document threads through every step, so the steps must run in order.
  test.describe.configure({ mode: "serial" });

  let documentId: string;

  test("a DEO uploads a degraded scan and the quality gate runs", async ({ page }) => {
    await signIn(page, USERS.deo);
    await page.goto("/deo/upload");

    // Fresh bytes: the seeded corpus already contains this page, and upload
    // refuses an exact duplicate (§22). See freshScan.
    await page.setInputFiles(
      'input[type="file"]',
      freshScan("datasets/generated/degraded/DOC-00022.jpg"),
    );
    await page.selectOption('select:near(:text("Document type"))', "KHASRA");
    await page.getByPlaceholder("1998-99").fill("1998-99");
    await page.getByPlaceholder("PARCEL-UP-DEMO-0142").fill(PARCEL);

    await page.getByRole("button", { name: /upload and check quality/i }).click();

    // Lands on the document page, whose URL carries the new id.
    await page.waitForURL(/\/deo\/documents\/DOC-\d+/);
    documentId = page.url().split("/").pop()!;
    expect(documentId).toMatch(/^DOC-\d+$/);

    // §22 — quality is measured before any model runs.
    await expect(page.getByText(/scan quality/i)).toBeVisible();
    await expect(page.getByText(/sharpness/i)).toBeVisible();
  });

  test("the AI pipeline extracts fields with provenance", async ({ page }) => {
    await signIn(page, USERS.deo);
    await page.goto(`/deo/documents/${documentId}`);

    await page.getByRole("button", { name: /start processing/i }).click();

    // Real OCR on a degraded page; give it room.
    await expect(page.getByText(/awaiting verification/i)).toBeVisible({
      timeout: 150_000,
    });
  });

  test("a verifier corrects a field and submits", async ({ page }) => {
    await signIn(page, USERS.verifier);

    // The document reached the queue by itself, not by being navigated to.
    await page.goto("/verifier/queue");
    await expect(page.getByText(documentId)).toBeVisible();

    await page.goto(`/verifier/documents/${documentId}`);

    // §28 — the scan and the fields are both on screen.
    await expect(page.getByRole("heading", { name: /extracted fields/i })).toBeVisible();

    // §26 — the raw OCR value is shown, never discarded. Labelled "Read from
    // page" since the provenance strip stopped speaking in pipeline jargon.
    await expect(page.getByText("Read from page").first()).toBeVisible();

    // Correct the first field. §30: the prediction survives the correction.
    const firstCorrect = page.getByRole("button", { name: "Correct" }).first();
    await firstCorrect.click();

    const input = page.locator('input[class*="record-text"]').first();
    await input.fill("verified-by-e2e");
    await page.getByRole("button", { name: /save correction/i }).click();

    await expect(page.getByText("Corrected").first()).toBeVisible();
    await expect(page.getByText(/the model predicted/i).first()).toBeVisible();

    // Then work the rest of the queue, which is what a verifier actually does.
    // The server refuses to submit while any field still needs review, and how
    // MANY need it depends on what OCR made of this particular scan -- so the
    // test clears them all rather than assuming a count. An earlier version
    // corrected one field and submitted, which passed only because that page
    // happened to have a single low-confidence field.
    const acceptButtons = page.getByRole("button", { name: "Accept" });
    for (
      let remaining = await acceptButtons.count();
      remaining > 0;
      remaining = await acceptButtons.count()
    ) {
      // Wait on the request, not on the button disappearing: the list
      // re-renders after each acceptance, so a locator captured beforehand
      // resolves to a different button and never settles.
      await Promise.all([
        page.waitForResponse(
          (response) =>
            response.url().includes("/approve") &&
            response.request().method() === "POST",
        ),
        acceptButtons.first().click(),
      ]);
      await expect
        .poll(() => acceptButtons.count(), { timeout: 15_000 })
        .toBeLessThan(remaining);
    }

    await page.getByRole("button", { name: /submit verification/i }).click();
    await expect(page.getByText(/now with the tehsildar/i)).toBeVisible();
  });

  test("a tehsildar sees the correction and approves", async ({ page }) => {
    await signIn(page, USERS.tehsildar);

    await page.goto("/tehsildar/approvals");
    await expect(page.getByText(documentId)).toBeVisible();

    await page.goto(`/tehsildar/approvals/${documentId}`);

    // §32 — the verifier's correction is visible to the approver. It appears
    // twice by design: once in the record's provenance strip and once in the
    // corrections table, so match the first rather than demanding uniqueness.
    await expect(page.getByText(/verifier corrections/i)).toBeVisible();
    await expect(page.getByText("verified-by-e2e").first()).toBeVisible();

    // The parcel's history is part of the decision, not a separate screen.
    await expect(page.getByText(/audit trail/i)).toBeVisible();

    await page.getByRole("button", { name: /approve this record/i }).click();
    await expect(page.getByText(/decision recorded/i)).toBeVisible();
  });

  test("the citizen sees the parcel, its map and its history", async ({ page }) => {
    await signIn(page, USERS.citizenA);

    // §14 — the parcel is on the holder's dashboard.
    await expect(page.getByText(/welcome/i)).toBeVisible();
    await expect(page.getByText(PARCEL)).toBeVisible();

    // §16 — and on the cadastral map.
    await page.goto(`/citizen/map?parcel=${PARCEL}`);
    await expect(page.locator("canvas")).toBeVisible({ timeout: 30_000 });

    // §25 / §40 — ownership history, with the mutation that caused each change.
    await page.goto(`/citizen/records/${PARCEL}`);
    await expect(page.getByText(/ownership and mutation history/i)).toBeVisible();
    await expect(page.getByText(/current holder/i).first()).toBeVisible();
  });

  test("the assistant answers from the database, with citations", async ({ page }) => {
    await signIn(page, USERS.citizenA);
    await page.goto("/citizen/assistant");

    await page.getByLabel("Your question").fill("Show my land parcels.");
    await page.getByRole("button", { name: "Ask" }).click();

    // §9 / §18 — an answer that cites the records it came from.
    await expect(page.getByText(/answered from/i)).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText(PARCEL).first()).toBeVisible();
  });

  test("the audit trail shows the whole history and verifies", async ({ page }) => {
    await signIn(page, USERS.tehsildar);
    await page.goto(`/audit/${documentId}`);

    // §41 — upload → AI → correction → verification → approval, in order.
    await expect(page.getByText(/document uploaded/i)).toBeVisible();
    await expect(page.getByText(/field corrected by a verifier/i)).toBeVisible();
    await expect(page.getByText(/verification submitted/i)).toBeVisible();
    await expect(page.getByText(/approved as the record of rights/i)).toBeVisible();

    await page.getByRole("button", { name: /verify the chain/i }).click();
    await expect(page.getByText(/the chain is intact/i)).toBeVisible({
      timeout: 30_000,
    });
  });
});

/**
 * §72 — the security test that must pass.
 *
 * Two citizens, two holdings. Neither may reach the other's.
 */
test.describe("citizen ownership isolation", () => {
  test("each citizen sees only their own parcels", async ({ page }) => {
    await signIn(page, USERS.citizenA);
    await page.goto("/citizen/my-land");
    const citizenAParcels = page.locator(".id").filter({ hasText: /^PARCEL-/ });
    await expect(citizenAParcels.first()).toBeVisible();
    const aParcels = await citizenAParcels.allInnerTexts();
    expect(aParcels.length).toBeGreaterThan(0);

    await signOut(page);
    await signIn(page, USERS.citizenB);
    await page.goto("/citizen/my-land");
    const citizenBParcels = page.locator(".id").filter({ hasText: /^PARCEL-/ });
    await expect(citizenBParcels.first()).toBeVisible();
    const bParcels = await citizenBParcels.allInnerTexts();
    expect(bParcels.length).toBeGreaterThan(0);

    const shared = aParcels.filter((p) => bParcels.includes(p));
    expect(shared, "two citizens are being shown the same holdings").toHaveLength(0);
  });

  test("a citizen cannot open another citizen's parcel", async ({ page }) => {
    await signIn(page, USERS.citizenB);
    // PARCEL is citizen A's. The refusal must not confirm it exists (§62).
    await page.goto(`/citizen/records/${PARCEL}`);
    await expect(page.getByText(/not recorded against your name/i)).toBeVisible();
  });

  test("a citizen cannot reach an officer section", async ({ page }) => {
    await signIn(page, USERS.citizenA);
    await page.goto("/verifier/queue");
    await expect(page.getByText(/you cannot open this/i)).toBeVisible();
  });

  test("a DEO cannot reach the tehsildar's analytics", async ({ page }) => {
    await signIn(page, USERS.deo);
    await page.goto("/tehsildar/analytics");
    await expect(page.getByText(/you cannot open this/i)).toBeVisible();
  });
});
