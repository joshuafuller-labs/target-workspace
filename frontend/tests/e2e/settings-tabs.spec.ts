/**
 * Settings tabs smoke test (tw-ypfy).
 *
 * Account & Security owns session-management and passkey primitives in
 * Settings. This smoke catches stale detours back to the standalone /account
 * page and keeps the auth surface discoverable from /settings.
 */

import { expect, test } from "@playwright/test";

test.skip(
  ({ viewport }) => !viewport || viewport.width < 768 || viewport.height < 600,
  "settings UI is desktop-only",
);

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  const email = page.locator('input[autocomplete="username"]');
  if (await email.count()) {
    await email.fill("admin@example.com");
    await page.locator('input[type="password"]').fill("demopw");
    await page.locator('button[type="submit"]').click();
    await page.waitForLoadState("networkidle");
  }
  await page.waitForTimeout(1500);
});

test("account security tab is reachable and shows auth controls", async ({
  page,
}) => {
  await page.goto("/settings");
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "Account & Security" }).click();
  await expect(
    page.getByRole("button", { name: /Revoke all sessions/i }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /Add passkey/i })).toBeVisible();
});
