import { expect, test, type Page } from "@playwright/test";

/**
 * §14 — the interface speaks Hindi or English, and the record does not change.
 *
 * The property worth a browser test is the one no unit test can reach: that
 * switching the INTERFACE language leaves record VALUES exactly as scanned.
 * Those are two different mechanisms that both say "language" in the UI, and
 * conflating them would mean a citizen could silently alter what a record
 * appears to say by changing a display preference.
 *
 * Requires the stack up (see playwright.config.ts).
 */

const PASSWORD = process.env.DEMO_PASSWORD ?? "demo_change_me";

// The seeded identities. Citizen accounts are named after the synthetic owner
// they belong to, so "citizen1@" does not exist.
const CITIZEN = "ram31@mrittika.demo";     // राम प्रसाद सिंह
const VERIFIER = "lekhpal@mrittika.demo";

async function signIn(page: Page, email: string) {
  // /login redirects a signed-in user away, so clear the session first --
  // sessionStorage is where the tokens live.
  await page.goto("/login");
  await page.evaluate(() => window.sessionStorage.clear());
  await page.goto("/login");
  await page.fill('input[name="email"]', email);
  await page.fill('input[name="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/(citizen|deo|verifier|tehsildar)\//);
}

/** The interface-language switcher, not the record-display one. */
function uiToggle(page: Page) {
  return page.getByRole("group", { name: /language|भाषा/i });
}

test.describe("the interface language (§14)", () => {
  test("a citizen lands in Hindi without choosing", async ({ page }) => {
    await page.context().clearCookies();
    await signIn(page, CITIZEN);
    await page.evaluate(() => window.localStorage.removeItem("mrittika.uiLanguage"));
    await page.goto("/citizen/my-land");

    await expect(page.getByRole("heading", { name: "मेरी भूमि" })).toBeVisible();
    await expect(page).toHaveTitle(/.*/);
    expect(await page.evaluate(() => document.documentElement.lang)).toBe("hi");
  });

  test("an officer lands in English without choosing", async ({ page }) => {
    await signIn(page, VERIFIER);
    await page.evaluate(() => window.localStorage.removeItem("mrittika.uiLanguage"));
    await page.goto("/verifier/queue");

    expect(await page.evaluate(() => document.documentElement.lang)).toBe("en");
    await expect(page.getByRole("link", { name: "Queue" })).toBeVisible();
  });

  test("the toggle switches the chrome both ways", async ({ page }) => {
    await signIn(page, CITIZEN);
    await page.goto("/citizen/my-land");

    await uiToggle(page).getByRole("button", { name: /English/i }).click();
    await expect(page.getByRole("heading", { name: "My land" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.lang)).toBe("en");

    await uiToggle(page).getByRole("button", { name: /हिन्दी|Hindi/i }).click();
    await expect(page.getByRole("heading", { name: "मेरी भूमि" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.lang)).toBe("hi");
  });

  test("the choice survives a reload", async ({ page }) => {
    await signIn(page, CITIZEN);
    await page.goto("/citizen/my-land");
    await uiToggle(page).getByRole("button", { name: /English/i }).click();
    await expect(page.getByRole("heading", { name: "My land" })).toBeVisible();

    await page.reload();
    await expect(page.getByRole("heading", { name: "My land" })).toBeVisible();
  });

  test("switching the interface does NOT change record values", async ({ page }) => {
    // The whole point. Record text is data, not chrome (§44).
    await signIn(page, CITIZEN);
    await page.goto("/citizen/my-land");

    // My land opens on the card view; the table is the other tab. The table is
    // what makes a value-by-value comparison possible.
    await page.getByRole("group", { name: /view|दृश्य/i })
      .getByRole("button", { name: /table|तालिका/i })
      .click();
    const table = page.getByRole("table");
    await expect(table).toBeVisible({ timeout: 15_000 });

    await uiToggle(page).getByRole("button", { name: /हिन्दी|Hindi/i }).click();
    await expect(page.getByRole("heading", { name: "मेरी भूमि" })).toBeVisible();
    const inHindi = await table.innerText();

    await uiToggle(page).getByRole("button", { name: /English/i }).click();
    await expect(page.getByRole("heading", { name: "My land" })).toBeVisible();
    const inEnglish = await table.innerText();

    // Column headings are chrome and DO change. The khasra numbers in the
    // cells are data and must not: they are matched out of both renderings
    // and compared.
    const numbers = (text: string) =>
      (text.match(/\d+\/?\d*/g) ?? []).filter((n) => n.length > 1).sort();
    expect(numbers(inHindi)).toEqual(numbers(inEnglish));
  });

  test("the officer interface can be read in Hindi too", async ({ page }) => {
    // The default is English, not a restriction.
    await signIn(page, VERIFIER);
    await page.goto("/verifier/queue");

    await uiToggle(page).getByRole("button", { name: /हिन्दी|Hindi/i }).click();
    expect(await page.evaluate(() => document.documentElement.lang)).toBe("hi");
    await expect(page.getByRole("link", { name: "कतार" })).toBeVisible();
  });
});
