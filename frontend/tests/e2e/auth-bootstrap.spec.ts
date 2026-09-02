import { expect, test } from "@playwright/test";

test("401 during auth bootstrap shows the empty login form", async ({ page }) => {
  await page.route("**/v1/auth/me", async (route) => {
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "user not found" }),
    });
  });

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(page.getByText("Something went wrong")).toBeHidden();

  const identifier = page.locator('input[autocomplete="username"]');
  await expect(identifier).toBeVisible();
  await expect(identifier).toHaveValue("");
  await expect(page.locator('input[type="password"]')).toHaveValue("");
});
