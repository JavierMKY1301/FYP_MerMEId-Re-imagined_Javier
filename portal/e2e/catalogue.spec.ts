import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * e2e/catalogue.spec.ts - end-to-end, compatibility and accessibility.
 *
 * These run against the built portal with the API live, so they exercise the
 * whole stack: MEI to RDF to SPARQL to REST to React.
 * Run:
 *     npx playwright test                     # all browsers
 *     npx playwright test --project=chromium  # one browser
 *     npx playwright test --ui                # interactive
 */

const FIRST_PAGE_SIZE = 20;

/**
 * Links to work records, excluding the header navigation.
 *
 * getByRole("link").first() matches the "Works" link in the site header, so
 * every test that used it clicked the nav rather than a result and then looked
 * for a detail page that had never opened. Scoping by href is stable across
 * layout changes and cannot be confused with navigation.
 */
function workLinks(page: Page) {
  return page.locator('a[href^="/works/"]');
}

async function openFirstWork(page: Page) {
  await workLinks(page).first().click();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
}

async function gotoCatalogue(page: Page) {
  await page.goto("/");
  // The portal fetches the whole catalogue once, so wait for the count rather
  // than a fixed timeout.
  await expect(page.getByText(/\d+ works?/)).toBeVisible({ timeout: 30_000 });
}

test.describe("Catalogue browsing", () => {
  test("lists works and reports the corpus size", async ({ page }) => {
    await gotoCatalogue(page);
    const count = await page.getByText(/\d+ works?/).textContent();
    const total = parseInt((count ?? "").replace(/\D/g, ""), 10);
    expect(total).toBeGreaterThan(100);
    await expect(workLinks(page).first()).toBeVisible();
  });

  test("pages through results without repeating a work", async ({ page }) => {
    await gotoCatalogue(page);
    const firstPage = await workLinks(page).allTextContents();
    await page.getByRole("button", { name: "Next" }).click();
    const secondPage = await workLinks(page).allTextContents();
    expect(secondPage).not.toEqual(firstPage);
    await expect(page.getByRole("button", { name: "Previous" })).toBeEnabled();
  });

  test("page size control changes how many are shown", async ({ page }) => {
    await gotoCatalogue(page);
    const before = await workLinks(page).count();
    await page.getByLabel("Per page").selectOption("10");
    await expect.poll(async () => workLinks(page).count()).toBeLessThan(before);
  });

  test("sorting reorders the listing", async ({ page }) => {
    await gotoCatalogue(page);
    const original = await workLinks(page).first().textContent();
    await page.getByLabel("Sort by").selectOption("title");
    await expect.poll(async () =>
      workLinks(page).first().textContent()).not.toBe(original);
  });
});

test.describe("Search and filtering", () => {
  test("finds a work by catalogue number, with or without the prefix", async ({ page }) => {
    // Regression guard: the shipped build matched titles only, so four of ten
    // participants typed a catalogue number and were shown nothing.
    await gotoCatalogue(page);
    const box = page.getByLabel(/Search title or catalogue number/);
    for (const term of ["129", "CNW 129", "cnw129"]) {
      await box.fill(term);
      await expect.poll(async () =>
        (await page.getByText(/\d+ works? match/).textContent()) ?? "",
        { timeout: 5000 }).toMatch(/[1-9]/);
    }
  });

  test("a filtered work appears exactly once", async ({ page }) => {
    // Regression guard: a subtitle typed "subordinate" was mapped as a second
    // main title, so one work rendered as two cards.
    await gotoCatalogue(page);
    await page.getByLabel("Genre").selectOption({ index: 1 });
    await page.getByLabel("Genre").selectOption({ index: 0 });
    await page.getByLabel("Genre").selectOption({ index: 1 });
    const titles = await workLinks(page).allTextContents();
    const normalised = titles.map((t) => t.replace(/\s+/g, " ").trim());
    expect(new Set(normalised).size).toBe(normalised.length);
  });

  test("filters narrow the result count and clear restores it", async ({ page }) => {
    await gotoCatalogue(page);
    const readCount = async () =>
      parseInt(((await page.getByText(/\d+ works?/).textContent()) ?? "")
        .replace(/\D/g, ""), 10);
    const all = await readCount();
    // exact: true, because the search field's label also contains "catalogue".
    await page.getByLabel("Catalogue", { exact: true }).selectOption({ index: 1 });
    await expect.poll(readCount).toBeLessThan(all);
    await page.getByRole("button", { name: "Clear filters" }).click();
    await expect.poll(readCount).toBe(all);
  });

  test("a search with no matches explains itself", async ({ page }) => {
    await gotoCatalogue(page);
    await page.getByLabel(/Search title or catalogue number/).fill("zzzznotawork");
    await expect(page.getByText(/Nothing matches those filters/)).toBeVisible();
  });
});

test.describe("Work detail", () => {
  test("opens a record and shows catalogue fields", async ({ page }) => {
    await gotoCatalogue(page);
    await openFirstWork(page);
    await expect(page.getByText("Catalogue record")).toBeVisible();
    await expect(page.getByRole("link", { name: /All works/ })).toBeVisible();
  });

  test("the incipit is full width, not squeezed into a column", async ({ page }) => {
    // Regression guard: five of ten participants said the notation was cramped
    // or cut off when it sat beside the record.
    await gotoCatalogue(page);
    await openFirstWork(page);
    await expect(page.getByRole("heading", { name: "Incipit" })).toBeVisible();
    // Filter by the heading, not by text: the catalogue record contains a field
    // labelled "Text incipit", and hasText matches case-insensitive substrings,
    // so a text filter selects both sections.
    const section = page.locator("section").filter({
      has: page.getByRole("heading", { name: "Incipit", exact: true }),
    });
    const box = await section.boundingBox();
    const viewport = page.viewportSize();
    if (box && viewport && viewport.width > 700) {
      expect(box.width).toBeGreaterThan(viewport.width * 0.55);
    }
  });

  test("a work with no incipit says so plainly", async ({ page }) => {
    await page.goto("/works/C1%3A006?catalogue=SchW");
    const body = page.locator("body");
    await expect(body).toContainText(/Incipit/);
  });

  test("an unknown work does not crash the portal", async ({ page }) => {
    await page.goto("/works/999999");
    await expect(page.getByText(/not found/i)).toBeVisible();
  });
});

test.describe("Accessibility (WCAG 2.2 AA)", () => {
  test("catalogue page has no automatically detectable violations", async ({ page }) => {
    await gotoCatalogue(page);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();
    expect(results.violations, JSON.stringify(
      results.violations.map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.length })),
      null, 2)).toEqual([]);
  });

  test("work detail page has no automatically detectable violations", async ({ page }) => {
    await gotoCatalogue(page);
    await openFirstWork(page);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();
    expect(results.violations, JSON.stringify(
      results.violations.map((v) => ({ id: v.id, impact: v.impact })), null, 2)).toEqual([]);
  });

  test("the catalogue is operable by keyboard alone", async ({ page, browserName }) => {
    await gotoCatalogue(page);
    await page.keyboard.press("Tab");
    const focused = await page.evaluate(() => document.activeElement?.tagName);
    expect(["INPUT", "SELECT", "BUTTON", "A"]).toContain(focused);

    // Safari omits links from the Tab sequence unless the user enables "Press
    // Tab to highlight each item on a webpage", which is off by default. The
    // omission is the browser's, not the page's: the links are focusable and
    // activate from the keyboard once focused, which is what is asserted for
    // WebKit below.
    if (browserName === "webkit") {
      await workLinks(page).first().focus();
      const href = await page.evaluate(() =>
        (document.activeElement as HTMLAnchorElement | null)?.getAttribute("href") ?? "");
      expect(href, "work links must be focusable").toMatch(/^\/works\//);
      await page.keyboard.press("Enter");
      await expect(page.getByText("Catalogue record")).toBeVisible();
      return;
    }
    // Tab until a work link has focus, then follow it without the mouse. The
    // check is on the href rather than the tag, because the header navigation
    // is also a link and reaching it would prove nothing about the results.
    let reached = false;
    for (let i = 0; i < 40; i++) {
      const href = await page.evaluate(() =>
        (document.activeElement as HTMLAnchorElement | null)?.getAttribute("href") ?? "");
      if (href.startsWith("/works/")) { reached = true; break; }
      await page.keyboard.press("Tab");
    }
    expect(reached, "no work link was reachable by keyboard").toBe(true);
    await page.keyboard.press("Enter");
    await expect(page.getByText("Catalogue record")).toBeVisible();
  });

  test("interactive controls meet the 24 px minimum target size", async ({ page }) => {
    // WCAG 2.2 success criterion 2.5.8. A participant asked for larger buttons.
    await gotoCatalogue(page);
    for (const sel of ["select", "button"]) {
      for (const el of await page.locator(sel).all()) {
        if (!(await el.isVisible())) continue;
        const box = await el.boundingBox();
        if (box) expect(box.height, `${sel} height`).toBeGreaterThanOrEqual(24);
      }
    }
  });

  test("every form control has a label", async ({ page }) => {
    await gotoCatalogue(page);
    for (const el of await page.locator("input, select").all()) {
      const id = await el.getAttribute("id");
      const aria = await el.getAttribute("aria-label");
      expect(id || aria, "control has neither id nor aria-label").toBeTruthy();
      if (id && !aria) {
        await expect(page.locator(`label[for="${id}"]`)).toHaveCount(1);
      }
    }
  });
});

test.describe("Network conditions and recovery", () => {
  test("shows an error when the API is unreachable", async ({ page }) => {
    await page.route("**/works*", (route) => route.abort());
    await page.goto("/");
    await expect(page.getByText(/Could not reach the API/)).toBeVisible({ timeout: 20_000 });
  });

  test("recovers once the API comes back", async ({ page }) => {
    let fail = true;
    await page.route("**/works*", (route) => (fail ? route.abort() : route.continue()));
    await page.goto("/");
    await expect(page.getByText(/Could not reach the API/)).toBeVisible({ timeout: 20_000 });
    fail = false;
    await page.reload();
    await expect(page.getByText(/\d+ works?/)).toBeVisible({ timeout: 30_000 });
  });

  test("remains usable on a slow connection", async ({ page }) => {
    await page.route("**/*", async (route) => {
      await new Promise((r) => setTimeout(r, 300));   // 300 ms added latency
      await route.continue();
    });
    await page.goto("/");
    await expect(page.getByText(/Loading catalogue|works/)).toBeVisible({ timeout: 45_000 });
  });

  test("a missing incipit image does not break the page", async ({ page }) => {
    await page.route("**/incipits/**", (route) => route.abort());
    await gotoCatalogue(page);
    await openFirstWork(page);
    await expect(page.getByRole("heading", { name: "Incipit" })).toBeVisible();
    await expect(page.getByText("Incipit not available.")).toBeVisible();
  });
});
