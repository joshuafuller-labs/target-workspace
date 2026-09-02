/**
 * User-admin UI e2e test (tw-6plp).
 *
 * Pins the contract: from a fresh login as admin, the Settings page
 * has a Users tab; you can create a user via a form; the user appears
 * in the list; you can disable them and verify they can't log in.
 *
 * Backend behavior is covered by test_user_crud.py — this test is
 * exclusively about the UI surface wiring it up.
 */

import { expect, test } from "@playwright/test";

// Skip on small/landscape projects — user admin is desktop chrome
// (the mobile drawer doesn't surface workspace settings management).
test.skip(
  ({ viewport }) =>
    !viewport || viewport.width < 768 || viewport.height < 600,
  "user-admin UI is desktop-only",
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

test("admin can create a user from the Users tab", async ({ page }) => {
  // Settings link lives in the {} API quick-links menu.
  await page.getByRole("button", { name: "Developer links" }).click();
  await page.getByRole("menuitem", { name: /Settings/ }).click();
  await page.waitForURL("**/settings");

  // Click Users tab.
  await page.getByRole("button", { name: "Users" }).click();

  // Click + New User.
  await page.getByRole("button", { name: /New user/i }).click();

  // Fill the form — scope queries to the dialog so we don't collide
  // with role <select>s in the row list behind the modal.
  const dialog = page.getByRole("dialog", { name: /new user/i });
  const stamp = Date.now();
  const newEmail = `created-${stamp}@example.com`;
  const displayName = `Created User ${stamp}`;
  await dialog.locator("#nu-email").fill(newEmail);
  await dialog.locator("#nu-name").fill(displayName);
  await dialog.locator("#nu-role").selectOption("operator");
  await dialog.locator("#nu-pw").fill("temp-pw-12345");
  await dialog.getByRole("button", { name: /^create$/i }).click();

  // Modal closes; new user appears in the list. Use first() to keep
  // the assertion stable even if previous test runs left rows.
  await expect(page.getByText(newEmail).first()).toBeVisible();
  await expect(page.getByText(displayName).first()).toBeVisible();
});

test("admin can disable a user, then login is blocked", async ({
  page,
  request,
}) => {
  // Provision via the API (faster than going through the UI again).
  const stamp = Date.now();
  const targetEmail = `to-disable-${stamp}@example.com`;
  const cookies = await page.context().cookies();
  const headers: Record<string, string> = {};
  if (cookies.length) {
    headers["Cookie"] = cookies.map((c) => `${c.name}=${c.value}`).join("; ");
  }
  const create = await request.post("/v1/users", {
    headers,
    data: {
      email: targetEmail,
      display_name: "Disable Me",
      role: "viewer",
      password: "p",
    },
  });
  expect(create.status()).toBe(201);

  // Navigate to Settings → Users.
  await page.getByRole("button", { name: "Developer links" }).click();
  await page.getByRole("menuitem", { name: /Settings/ }).click();
  await page.waitForURL("**/settings");
  await page.getByRole("button", { name: "Users" }).click();

  // Find the row by email. The user list is a <ul> with one <li>
  // per user; scope strictly so we don't match an ancestor <div>.
  const row = page.locator("li").filter({ hasText: targetEmail }).first();
  await row.getByRole("button", { name: /^disable$/i }).click();
  // Row state should flip to "Disabled" or the toggle button to "Enable".
  await expect(
    row.getByRole("button", { name: /enable/i }),
  ).toBeVisible();

  // Confirm via the API: a login attempt as the disabled user → 401.
  const logout = await request.post("/v1/auth/logout", { headers });
  expect(logout.status()).toBeLessThan(500);
  const login = await request.post("/v1/auth/login", {
    data: { email: targetEmail, password: "p" },
  });
  expect(login.status()).toBe(401);
});
