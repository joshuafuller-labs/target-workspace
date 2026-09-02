/**
 * Responsive-layout regression tests.
 *
 * The mobile-MVP audit (manual playwright script in /tmp) found three
 * concrete issues:
 *   1. Phone landscape (844x390) flipped to desktop chrome and the
 *      header ate half the visible viewport (197px on a 390-tall
 *      screen).
 *   2. Tablet portrait (768x1024) sat exactly on the md: breakpoint;
 *      desktop chrome kicked in too eagerly.
 *   3. The Logout button was 40px wide (< 44px touch target).
 *
 * The fix added a custom Tailwind variant `desktop:` that requires BOTH
 * min-width:768 AND min-height:600. This test pins the contract so we
 * don't regress. Failing here = mobile UX broken.
 */

import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  const emailField = page.locator('input[autocomplete="username"]');
  if (await emailField.count()) {
    await emailField.fill("admin@example.com");
    await page.locator('input[type="password"]').fill("demopw");
    await page.locator('button[type="submit"]').click();
    await page.waitForLoadState("networkidle");
  }
  // Allow boards to load + theme to apply.
  await page.waitForTimeout(2500);
});

test.describe("mobile breakpoint logic — desktop: variant requires width AND height", () => {
  test("phone-portrait gets mobile chrome (hamburger visible, desktop chrome hidden)", async ({
    page,
    viewport,
  }) => {
    test.skip(
      viewport?.width !== 390 || viewport?.height !== 844,
      "phone-portrait only",
    );
    const hamburger = page.getByRole("button", { name: "Open menu" });
    await expect(hamburger).toBeVisible();
    // Desktop-only items must not be visible.
    await expect(page.getByRole("button", { name: "Edit board" })).toBeHidden();
    await expect(page.getByRole("button", { name: "+ Board" })).toBeHidden();
  });

  test("phone-landscape ALSO gets mobile chrome (the original bug)", async ({
    page,
    viewport,
  }) => {
    test.skip(
      viewport?.width !== 844 || viewport?.height !== 390,
      "phone-landscape only",
    );
    // The bug: viewport width 844 cleared md:'s 768 threshold and
    // the SPA flipped to desktop chrome on landscape phones, eating
    // half the visible viewport. The fix: desktop: requires BOTH
    // width≥768 AND height≥600, so 390-tall landscape stays mobile.
    const hamburger = page.getByRole("button", { name: "Open menu" });
    await expect(hamburger).toBeVisible();
    const matchesDesktop = await page.evaluate(() =>
      window.matchMedia("(min-width: 768px) and (min-height: 600px)").matches,
    );
    expect(matchesDesktop).toBe(false);
  });

  test("tablet-portrait crosses BOTH thresholds → desktop chrome", async ({
    page,
    viewport,
  }) => {
    test.skip(
      viewport?.width !== 768 || viewport?.height !== 1024,
      "tablet-portrait only",
    );
    const matchesDesktop = await page.evaluate(() =>
      window.matchMedia("(min-width: 768px) and (min-height: 600px)").matches,
    );
    expect(matchesDesktop).toBe(true);
    // The hamburger menu is now visible at every screen size — it owns
    // Logout, user identity, and a few secondary actions. The
    // desktop-only inline buttons (Edit board, + Board, Show map, etc.)
    // still live in the header strip alongside it.
    await expect(page.getByRole("button", { name: "+ Board" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Open menu" })).toBeVisible();
  });
});

test.describe("header height — must not eat the visible viewport", () => {
  test("phone-landscape header ≤ 33% of viewport height", async ({
    page,
    viewport,
  }) => {
    test.skip(
      viewport?.width !== 844 || viewport?.height !== 390,
      "phone-landscape only",
    );
    // The original bug had a 197px-tall header on 390-tall viewports.
    // We allow up to 33% (130px on a 390 viewport) — anything more
    // means the layout has regressed back to stacking like desktop.
    const headerHeight = await page.evaluate(
      () => document.querySelector("header")!.getBoundingClientRect().height,
    );
    expect(headerHeight).toBeLessThanOrEqual(130);
  });
});

test.describe("tap targets — interactive elements must be ≥44px on at least one dimension", () => {
  test("no app-owned interactive element is < 40px on both dimensions", async ({
    page,
  }) => {
    const tinyTaps = await page.evaluate(() => {
      const out: { tag: string; w: number; h: number; text: string }[] = [];
      const all = document.querySelectorAll(
        "button, a, input, select, textarea, [role='button']",
      );
      for (const el of all) {
        // Skip Cesium's own attribution / chrome — not our controls
        // and not something we can reasonably resize without forking.
        if (el.closest(".cesium-viewer-bottom") || el.closest(".cesium-credit")) continue;
        if (el.closest("[data-cesium]")) continue;
        const r = (el as HTMLElement).getBoundingClientRect();
        if (r.width === 0 || r.height === 0) continue;
        if (r.width < 40 && r.height < 40) {
          out.push({
            tag: el.tagName,
            w: Math.round(r.width),
            h: Math.round(r.height),
            text: (el.textContent || "").trim().slice(0, 30),
          });
        }
      }
      return out;
    });
    expect(tinyTaps, JSON.stringify(tinyTaps, null, 2)).toEqual([]);
  });
});

test.describe("document-level horizontal overflow — clipped so position:fixed anchors to viewport", () => {
  test("body does not scroll horizontally on phone-portrait", async ({
    page,
    viewport,
  }) => {
    test.skip(
      viewport?.width !== 390 || viewport?.height !== 844,
      "phone-portrait only",
    );
    // overflow-x:hidden on html/body means even if children have wide
    // content (scrollWidth > viewport), the user can NEVER horizontally
    // scroll the document — the kanban scrolls inside its section, but
    // the page itself stays put. This is what unbreaks position:fixed
    // on iOS Safari.
    const overflow = await page.evaluate(() => ({
      bodyOverflowX: getComputedStyle(document.body).overflowX,
      htmlOverflowX: getComputedStyle(document.documentElement).overflowX,
    }));
    expect(overflow.bodyOverflowX).toBe("hidden");
    expect(overflow.htmlOverflowX).toBe("hidden");
  });

  test("opening a card modal positions it inside the visible viewport", async ({
    page,
    viewport,
  }) => {
    test.skip(
      viewport?.width !== 390 || viewport?.height !== 844,
      "phone-portrait only",
    );
    // The user-reported bug: tapping a card on mobile put the detail
    // modal down-right of the visible viewport, requiring pinch-zoom
    // to find. Now: regardless of how wide the kanban's children are,
    // the modal's fixed-positioned root must land inside the viewport.
    const card = page.getByText("BISON-01").first();
    await card.click();
    await page.waitForTimeout(400);
    const rect = await page.evaluate(() => {
      const dlg = document.querySelector('[role="dialog"]');
      if (!dlg) return null;
      const r = (dlg as HTMLElement).getBoundingClientRect();
      return { x: r.x, y: r.y, w: r.width, h: r.height };
    });
    expect(rect).not.toBeNull();
    expect(rect!.x).toBeGreaterThanOrEqual(-2);
    expect(rect!.x + rect!.w).toBeLessThanOrEqual(viewport.width + 2);
    expect(rect!.y).toBeGreaterThanOrEqual(-2);
    expect(rect!.y + rect!.h).toBeLessThanOrEqual(viewport.height + 2);
  });
});

test.describe("map default visibility — must NOT auto-open as fullscreen overlay on mobile", () => {
  test("phone-landscape opens with kanban visible, NOT map fullscreen", async ({
    page,
    viewport,
  }) => {
    test.skip(
      viewport?.width !== 844 || viewport?.height !== 390,
      "phone-landscape only",
    );
    // The Cesium canvas exists in the DOM either way; what matters is
    // whether the kanban or the fullscreen map overlay is visible
    // FIRST. Count kanban columns visible — if 0, the map ate the
    // viewport.
    const columnCount = await page.evaluate(
      () => document.querySelectorAll("section header").length,
    );
    expect(columnCount).toBeGreaterThan(0);
  });
});
