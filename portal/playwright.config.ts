import { defineConfig, devices } from "@playwright/test";

/**
 * playwright.config.ts
 *
 * The project list is the compatibility matrix. Every test in e2e/ runs once
 * per project, so a single 'npx playwright test' produces evidence across three
 * rendering engines and two mobile viewports rather than one browser on one
 * screen size.
 *
 * Chromium, Firefox and WebKit are the three independent engines in use today,
 * so they cover Chrome and Edge, Firefox, and Safari respectively. The two
 * device profiles matter because the portal's layout changes at breakpoints
 * and because WCAG 2.2 target-size rules are easiest to fail on a phone.
 *
 * The web server block starts the portal automatically. The API must already
 * be running, since it holds the graph and takes a few seconds to build its
 * caches.
 *
 * Run:
 *     cd prototype && py -m uvicorn api.main:app --port 8000     # first
 *     cd portal && npx playwright install                        # once
 *     npx playwright test
 *     npx playwright show-report
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  timeout: 60_000,
  expect: { timeout: 10_000 },

  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },

  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
    { name: "mobile-chrome", use: { ...devices["Pixel 5"] } },
    { name: "mobile-safari", use: { ...devices["iPhone 13"] } },
  ],

  webServer: {
    command: "npm run dev",
    url: "http://localhost:5173",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
