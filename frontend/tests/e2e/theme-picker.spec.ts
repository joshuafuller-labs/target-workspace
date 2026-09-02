/**
 * Regression test: clicking a theme tile in Settings → Theme commits
 * the selection and the "Current" indicator moves to the clicked tile.
 *
 * The original bug: tiles only previewed on hover (onMouseEnter →
 * applyTheme), but had no onClick — so the user could *see* a theme
 * apply, but the "Current" badge stayed on the saved theme and the
 * change vanished on mouseLeave. The hint text said "commit via the
 * board edit form" which made the picker non-obviously broken.
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

test("clicking a theme tile commits the selection", async ({ page }) => {
  await page.goto("/settings");
  await page.getByRole("button", { name: "Theme" }).click();

  // Establish a known starting point — click Neutral first regardless
  // of current state, then click Tactical and assert the swap. Test is
  // idempotent across runs (the DB persists per-board theme).
  await page.getByRole("button", { name: /^Neutral/ }).click();
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(400);
  await expect(
    page.getByRole("button", { name: /^Neutral/ }).getByText("Current"),
  ).toBeVisible();

  const target = page.getByRole("button", { name: /^Tactical/ });
  await target.click();
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(400);
  // Move the mouse off the tile so any lingering hover/focus state
  // can't mask a CSS revert. This is exactly the scenario where the
  // original useEffect-cleanup race fired: the cleanup ran with the
  // stale closure and re-applied the previous theme.
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  await page.waitForTimeout(200);

  // After clicking Tactical, that tile reports Current and Neutral does not.
  await expect(target.getByText("Current")).toBeVisible();
  await expect(
    page.getByRole("button", { name: /^Neutral/ }).getByText("Current"),
  ).toHaveCount(0);

  // CSS variables actually reflect the clicked theme — not just the badge.
  // The previous race condition would leave data-tw on the old value
  // even though the badge appeared correct.
  await expect(page.locator("html")).toHaveAttribute("data-tw", "tactical");

  // Reload and confirm persistence — the selection survives a refresh.
  await page.reload();
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "Theme" }).click();
  await expect(
    page.getByRole("button", { name: /^Tactical/ }).getByText("Current"),
  ).toBeVisible();
});
