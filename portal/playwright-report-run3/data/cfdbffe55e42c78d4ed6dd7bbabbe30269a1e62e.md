# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: catalogue.spec.ts >> Work detail >> the incipit is full width, not squeezed into a column
- Location: e2e\catalogue.spec.ts:147:3

# Error details

```
Error: locator.boundingBox: Error: strict mode violation: locator('section').filter({ hasText: 'Incipit' }) resolved to 2 elements:
    1) <section>…</section> aka getByText('Catalogue recordComposerCarl')
    2) <section class="mt-8">…</section> aka getByText('IncipitThe opening bars, as')

Call log:
  - waiting for locator('section').filter({ hasText: 'Incipit' })

```

# Page snapshot

```yaml
- generic [ref=e3]:
  - banner [ref=e4]:
    - generic [ref=e5]:
      - generic [ref=e6]:
        - generic [ref=e7]: MerMEId Re-imagined
        - generic [ref=e8]: Danish Centre for Music Editing catalogues - Linked Data portal
      - link "Works" [ref=e9]:
        - /url: /
      - link "Evaluation" [ref=e10]:
        - /url: /evaluation
      - generic [ref=e11]: 65,376 triples . rdflib
  - main [ref=e12]:
    - article [ref=e13]:
      - link "← All works" [ref=e14]:
        - /url: /
      - heading "Saul and David" [level=1] [ref=e15]
      - paragraph [ref=e16]: CNW 1 · Carl Nielsen (CNW)
      - generic [ref=e17]:
        - generic [ref=e18]:
          - heading "Catalogue record" [level=2] [ref=e19]
          - generic [ref=e20]:
            - generic [ref=e21]:
              - term [ref=e22]: Composer
              - definition [ref=e23]: Carl Nielsen
            - generic [ref=e24]:
              - term [ref=e25]: Composed
              - definition [ref=e26]: 1899–1901
            - generic [ref=e27]:
              - term [ref=e28]: Tempo
              - definition [ref=e29]: Allegro
            - generic [ref=e30]:
              - term [ref=e31]: Metre
              - definition [ref=e32]: 3/4
            - generic [ref=e33]:
              - term [ref=e34]: Genre
              - definition [ref=e35]: Opera, Stage music
            - generic [ref=e36]:
              - term [ref=e37]: Scoring
              - definition [ref=e38]: A., B., B.Bar., S., T., arpa, camp., cb., cl., cl.b., cor., fg., fl., fl./fl.picc., gr.c., ob., ob./cor.ingl., ptti., tam., tb., timp., tr., trb.b., trb.t., trgl., va., vc., vl.1, vl.2
            - generic [ref=e39]:
              - term [ref=e40]: Text incipit
              - definition [ref=e41]: Abner! Svar, er det dig?
        - generic [ref=e42]:
          - heading "External identifiers" [level=2] [ref=e43]
          - generic [ref=e44]:
            - link "Wikidata ↗" [ref=e45]:
              - /url: http://www.wikidata.org/entity/Q205139
            - link "VIAF ↗" [ref=e46]:
              - /url: https://viaf.org/viaf/197250
          - paragraph [ref=e47]: Composer-level links are verified via VIAF. Work-level matches are stored separately with a confidence score (see Evaluation).
          - heading "Editorial notes" [level=2] [ref=e48]
          - paragraph [ref=e49]: M. Phil. diss.
          - paragraph [ref=e50]: Magisterafhandling.
          - paragraph [ref=e51]: Ph.D. diss.
          - paragraph [ref=e52]: Speciale.
          - paragraph [ref=e53]: Typewritten undated manuscript, presumably intended for Carl Nielsen's autobiography
      - generic [ref=e54]:
        - heading "Incipit" [level=2] [ref=e55]
        - paragraph [ref=e56]: The opening bars, as recorded by the catalogue to identify the work. Full scores are not part of the published dataset.
        - img "Opening bars of Saul and David" [ref=e59]
  - contentinfo [ref=e60]:
    - generic [ref=e61]: "Data: thematic catalogues of Carl Nielsen, Niels W. Gade, J.P.E. Hartmann and J.A. Scheibe, created 2010-2020 by the Danish Centre for Music Editing, Royal Danish Library, and released as MEI under CC0. CM3070 project."
```

# Test source

```ts
  54  |   // The portal fetches the whole catalogue once, so wait for the count rather
  55  |   // than a fixed timeout.
  56  |   await expect(page.getByText(/\d+ works?/)).toBeVisible({ timeout: 30_000 });
  57  | }
  58  | 
  59  | test.describe("Catalogue browsing", () => {
  60  |   test("lists works and reports the corpus size", async ({ page }) => {
  61  |     await gotoCatalogue(page);
  62  |     const count = await page.getByText(/\d+ works?/).textContent();
  63  |     const total = parseInt((count ?? "").replace(/\D/g, ""), 10);
  64  |     expect(total).toBeGreaterThan(100);
  65  |     await expect(workLinks(page).first()).toBeVisible();
  66  |   });
  67  | 
  68  |   test("pages through results without repeating a work", async ({ page }) => {
  69  |     await gotoCatalogue(page);
  70  |     const firstPage = await workLinks(page).allTextContents();
  71  |     await page.getByRole("button", { name: "Next" }).click();
  72  |     const secondPage = await workLinks(page).allTextContents();
  73  |     expect(secondPage).not.toEqual(firstPage);
  74  |     await expect(page.getByRole("button", { name: "Previous" })).toBeEnabled();
  75  |   });
  76  | 
  77  |   test("page size control changes how many are shown", async ({ page }) => {
  78  |     await gotoCatalogue(page);
  79  |     const before = await workLinks(page).count();
  80  |     await page.getByLabel("Per page").selectOption("10");
  81  |     await expect.poll(async () => workLinks(page).count()).toBeLessThan(before);
  82  |   });
  83  | 
  84  |   test("sorting reorders the listing", async ({ page }) => {
  85  |     await gotoCatalogue(page);
  86  |     const original = await workLinks(page).first().textContent();
  87  |     await page.getByLabel("Sort by").selectOption("title");
  88  |     await expect.poll(async () =>
  89  |       workLinks(page).first().textContent()).not.toBe(original);
  90  |   });
  91  | });
  92  | 
  93  | test.describe("Search and filtering", () => {
  94  |   test("finds a work by catalogue number, with or without the prefix", async ({ page }) => {
  95  |     // Regression guard: the shipped build matched titles only, so four of ten
  96  |     // participants typed a catalogue number and were shown nothing.
  97  |     await gotoCatalogue(page);
  98  |     const box = page.getByLabel(/Search title or catalogue number/);
  99  |     for (const term of ["129", "CNW 129", "cnw129"]) {
  100 |       await box.fill(term);
  101 |       await expect.poll(async () =>
  102 |         (await page.getByText(/\d+ works? match/).textContent()) ?? "",
  103 |         { timeout: 5000 }).toMatch(/[1-9]/);
  104 |     }
  105 |   });
  106 | 
  107 |   test("a filtered work appears exactly once", async ({ page }) => {
  108 |     // Regression guard: a subtitle typed "subordinate" was mapped as a second
  109 |     // main title, so one work rendered as two cards.
  110 |     await gotoCatalogue(page);
  111 |     await page.getByLabel("Genre").selectOption({ index: 1 });
  112 |     await page.getByLabel("Genre").selectOption({ index: 0 });
  113 |     await page.getByLabel("Genre").selectOption({ index: 1 });
  114 |     const titles = await workLinks(page).allTextContents();
  115 |     const normalised = titles.map((t) => t.replace(/\s+/g, " ").trim());
  116 |     expect(new Set(normalised).size).toBe(normalised.length);
  117 |   });
  118 | 
  119 |   test("filters narrow the result count and clear restores it", async ({ page }) => {
  120 |     await gotoCatalogue(page);
  121 |     const readCount = async () =>
  122 |       parseInt(((await page.getByText(/\d+ works?/).textContent()) ?? "")
  123 |         .replace(/\D/g, ""), 10);
  124 |     const all = await readCount();
  125 |     // exact: true, because the search field's label also contains "catalogue".
  126 |     await page.getByLabel("Catalogue", { exact: true }).selectOption({ index: 1 });
  127 |     await expect.poll(readCount).toBeLessThan(all);
  128 |     await page.getByRole("button", { name: "Clear filters" }).click();
  129 |     await expect.poll(readCount).toBe(all);
  130 |   });
  131 | 
  132 |   test("a search with no matches explains itself", async ({ page }) => {
  133 |     await gotoCatalogue(page);
  134 |     await page.getByLabel(/Search title or catalogue number/).fill("zzzznotawork");
  135 |     await expect(page.getByText(/Nothing matches those filters/)).toBeVisible();
  136 |   });
  137 | });
  138 | 
  139 | test.describe("Work detail", () => {
  140 |   test("opens a record and shows catalogue fields", async ({ page }) => {
  141 |     await gotoCatalogue(page);
  142 |     await openFirstWork(page);
  143 |     await expect(page.getByText("Catalogue record")).toBeVisible();
  144 |     await expect(page.getByRole("link", { name: /All works/ })).toBeVisible();
  145 |   });
  146 | 
  147 |   test("the incipit is full width, not squeezed into a column", async ({ page }) => {
  148 |     // Regression guard: five of ten participants said the notation was cramped
  149 |     // or cut off when it sat beside the record.
  150 |     await gotoCatalogue(page);
  151 |     await openFirstWork(page);
  152 |     await expect(page.getByRole("heading", { name: "Incipit" })).toBeVisible();
  153 |     const section = page.locator("section").filter({ hasText: "Incipit" });
> 154 |     const box = await section.boundingBox();
      |                               ^ Error: locator.boundingBox: Error: strict mode violation: locator('section').filter({ hasText: 'Incipit' }) resolved to 2 elements:
  155 |     const viewport = page.viewportSize();
  156 |     if (box && viewport && viewport.width > 700) {
  157 |       expect(box.width).toBeGreaterThan(viewport.width * 0.55);
  158 |     }
  159 |   });
  160 | 
  161 |   test("a work with no incipit says so plainly", async ({ page }) => {
  162 |     await page.goto("/works/C1%3A006?catalogue=SchW");
  163 |     const body = page.locator("body");
  164 |     await expect(body).toContainText(/Incipit/);
  165 |   });
  166 | 
  167 |   test("an unknown work does not crash the portal", async ({ page }) => {
  168 |     await page.goto("/works/999999");
  169 |     await expect(page.getByText(/not found/i)).toBeVisible();
  170 |   });
  171 | });
  172 | 
  173 | test.describe("Accessibility (WCAG 2.2 AA)", () => {
  174 |   test("catalogue page has no automatically detectable violations", async ({ page }) => {
  175 |     await gotoCatalogue(page);
  176 |     const results = await new AxeBuilder({ page })
  177 |       .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
  178 |       .analyze();
  179 |     expect(results.violations, JSON.stringify(
  180 |       results.violations.map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.length })),
  181 |       null, 2)).toEqual([]);
  182 |   });
  183 | 
  184 |   test("work detail page has no automatically detectable violations", async ({ page }) => {
  185 |     await gotoCatalogue(page);
  186 |     await openFirstWork(page);
  187 |     const results = await new AxeBuilder({ page })
  188 |       .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
  189 |       .analyze();
  190 |     expect(results.violations, JSON.stringify(
  191 |       results.violations.map((v) => ({ id: v.id, impact: v.impact })), null, 2)).toEqual([]);
  192 |   });
  193 | 
  194 |   test("the catalogue is operable by keyboard alone", async ({ page }) => {
  195 |     await gotoCatalogue(page);
  196 |     await page.keyboard.press("Tab");
  197 |     const focused = await page.evaluate(() => document.activeElement?.tagName);
  198 |     expect(["INPUT", "SELECT", "BUTTON", "A"]).toContain(focused);
  199 |     // Tab until a work link has focus, then follow it without the mouse. The
  200 |     // check is on the href rather than the tag, because the header navigation
  201 |     // is also a link and reaching it would prove nothing about the results.
  202 |     let reached = false;
  203 |     for (let i = 0; i < 40; i++) {
  204 |       const href = await page.evaluate(() =>
  205 |         (document.activeElement as HTMLAnchorElement | null)?.getAttribute("href") ?? "");
  206 |       if (href.startsWith("/works/")) { reached = true; break; }
  207 |       await page.keyboard.press("Tab");
  208 |     }
  209 |     expect(reached, "no work link was reachable by keyboard").toBe(true);
  210 |     await page.keyboard.press("Enter");
  211 |     await expect(page.getByText("Catalogue record")).toBeVisible();
  212 |   });
  213 | 
  214 |   test("interactive controls meet the 24 px minimum target size", async ({ page }) => {
  215 |     // WCAG 2.2 success criterion 2.5.8. A participant asked for larger buttons.
  216 |     await gotoCatalogue(page);
  217 |     for (const sel of ["select", "button"]) {
  218 |       for (const el of await page.locator(sel).all()) {
  219 |         if (!(await el.isVisible())) continue;
  220 |         const box = await el.boundingBox();
  221 |         if (box) expect(box.height, `${sel} height`).toBeGreaterThanOrEqual(24);
  222 |       }
  223 |     }
  224 |   });
  225 | 
  226 |   test("every form control has a label", async ({ page }) => {
  227 |     await gotoCatalogue(page);
  228 |     for (const el of await page.locator("input, select").all()) {
  229 |       const id = await el.getAttribute("id");
  230 |       const aria = await el.getAttribute("aria-label");
  231 |       expect(id || aria, "control has neither id nor aria-label").toBeTruthy();
  232 |       if (id && !aria) {
  233 |         await expect(page.locator(`label[for="${id}"]`)).toHaveCount(1);
  234 |       }
  235 |     }
  236 |   });
  237 | });
  238 | 
  239 | test.describe("Network conditions and recovery", () => {
  240 |   test("shows an error when the API is unreachable", async ({ page }) => {
  241 |     await page.route("**/works*", (route) => route.abort());
  242 |     await page.goto("/");
  243 |     await expect(page.getByText(/Could not reach the API/)).toBeVisible({ timeout: 20_000 });
  244 |   });
  245 | 
  246 |   test("recovers once the API comes back", async ({ page }) => {
  247 |     let fail = true;
  248 |     await page.route("**/works*", (route) => (fail ? route.abort() : route.continue()));
  249 |     await page.goto("/");
  250 |     await expect(page.getByText(/Could not reach the API/)).toBeVisible({ timeout: 20_000 });
  251 |     fail = false;
  252 |     await page.reload();
  253 |     await expect(page.getByText(/\d+ works?/)).toBeVisible({ timeout: 30_000 });
  254 |   });
```