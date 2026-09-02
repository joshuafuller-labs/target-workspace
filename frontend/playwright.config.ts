import { defineConfig } from "@playwright/test";

/**
 * E2E test config. Runs against the local stack (docker compose up -d
 * app from the repo root). Tests live in tests/e2e/.
 *
 * Three projects cover the responsive matrix: phone portrait, phone
 * landscape, tablet portrait. We deliberately do NOT use Playwright's
 * `isMobile: true` device emulation because it sets a separate visual
 * viewport that confuses our media-query logic — plain `viewport`
 * matches what a real browser at that size would do.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: "list",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  use: {
    baseURL: "http://127.0.0.1:8000",
    trace: "off",
    timezoneId: "America/New_York",
  },
  projects: [
    {
      name: "phone-portrait",
      use: { viewport: { width: 390, height: 844 }, hasTouch: true },
    },
    {
      name: "phone-landscape",
      use: { viewport: { width: 844, height: 390 }, hasTouch: true },
    },
    {
      name: "tablet-portrait",
      use: { viewport: { width: 768, height: 1024 }, hasTouch: true },
    },
    {
      name: "desktop",
      use: { viewport: { width: 1280, height: 800 } },
    },
    // tw-y60: viewport matrix per ADR 0011. Each runs the
    // shared overflow / tap-target / hamburger contracts.
    {
      name: "phone-360x800",
      use: { viewport: { width: 360, height: 800 }, hasTouch: true },
      testMatch: /viewport-matrix\.spec\.ts$/,
    },
    {
      name: "phone-412x915",
      use: { viewport: { width: 412, height: 915 }, hasTouch: true },
      testMatch: /viewport-matrix\.spec\.ts$/,
    },
    {
      name: "tablet-720x1024",
      use: { viewport: { width: 720, height: 1024 }, hasTouch: true },
      testMatch: /viewport-matrix\.spec\.ts$/,
    },
    {
      name: "tablet-1024x720",
      use: { viewport: { width: 1024, height: 720 }, hasTouch: true },
      testMatch: /viewport-matrix\.spec\.ts$/,
    },
    {
      name: "desktop-1440x900",
      use: { viewport: { width: 1440, height: 900 } },
      testMatch: /viewport-matrix\.spec\.ts$/,
    },
    {
      name: "desktop-1920x1080",
      use: { viewport: { width: 1920, height: 1080 } },
      testMatch: /viewport-matrix\.spec\.ts$/,
    },
    {
      // Reproduces the user-reported Android Chrome modal bug.
      // where the layout viewport inflated to 1772px on a 443-wide
      // device, throwing `position: fixed; inset: 0` modals off-screen.
      // isMobile: true is what triggers that mobile-Chrome behavior in
      // Chromium — without it the bug is invisible to the test runner.
      // Only mobile-modal.spec.ts opts into this project.
      name: "android-chrome",
      testMatch: /mobile-modal\.spec\.ts$/,
      use: {
        viewport: { width: 443, height: 811 },
        deviceScaleFactor: 2.625,
        isMobile: true,
        hasTouch: true,
        userAgent:
          "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 " +
          "(KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36",
      },
    },
  ],
});
