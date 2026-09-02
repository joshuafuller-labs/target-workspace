/**
 * Regression test for the mobile modal rendering off-screen on Android Chrome.
 *
 * The bug: tapping a card on Chrome Android opened the TargetDetail modal
 * far down and to the right of the visible viewport. The user had to
 * pinch-zoom out to find it. Pre-fix diagnostic readout from the user's
 * actual device:
 *
 *   BEFORE click: innerW=1772 innerH=3244  vv.width=443 vv.scale=1
 *                 docClientW=443 docScrollW=2043
 *   AFTER click:  dialog.x=0 dialog.y=0 dialog.w=1772 dialog.h=3244
 *                 inner.x=550 inner.y=2497 inner.w=672 inner.h=746
 *
 * Root cause: `position: fixed; inset: 0` resolves against
 * `window.innerWidth × window.innerHeight`. On Android Chrome, when page
 * content has `scrollWidth > viewport width`, the layout viewport
 * inflates to match the content — so `inset: 0` no longer means "the
 * visible screen", it means "the inflated 1772×3244 box". The flex
 * `items-end justify-center` then places the modal inner at x=550 y=2497,
 * which is far outside the user's 443×811 screen.
 *
 * Fix: swap `fixed inset-0` for `fixed top-0 left-0 w-[100dvw] h-[100dvh]`.
 * The `dvw`/`dvh` (dynamic viewport) units track the *visible* viewport
 * and don't follow the inflated layout viewport.
 *
 * This spec runs in the `android-chrome` project (isMobile: true), which
 * is the configuration that actually reproduces the inflation. Without
 * `isMobile: true` the bug is invisible to Playwright.
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
  await page.waitForTimeout(2500);
});

/**
 * Sanity check the test itself has teeth — inject CSS that undoes the
 * fix and confirm the page enters the broken state under android-chrome.
 * If this stops failing the way it should, the regression test above
 * is no longer guarding anything.
 */
test("sanity: removing contain:paint and reverting columns to vw reproduces inflation", async ({
  page,
}) => {
  await page.goto("/");
  const emailField = page.locator('input[autocomplete="username"]');
  if (await emailField.count()) {
    await emailField.fill("admin@example.com");
    await page.locator('input[type="password"]').fill("demopw");
    await page.locator('button[type="submit"]').click();
    await page.waitForLoadState("networkidle");
  }
  await page.waitForTimeout(2500);
  await page.addStyleTag({
    content: `
      /* Undo the fix: kill containment + go back to vw-sized columns */
      section.overflow-x-auto { contain: none !important; }
      [class*="w-[88dvw]"] { width: 88vw !important; min-width: 88vw !important; }
    `,
  });
  await page.waitForTimeout(300);
  const broken = await page.evaluate(() => ({
    docScrollW: document.documentElement.scrollWidth,
    docClientW: document.documentElement.clientWidth,
    innerW: window.innerWidth,
    vvW: window.visualViewport?.width ?? null,
  }));
  // Under the broken state, doc overflows and Chrome inflates innerW.
  // (This is what the user saw on their actual device.)
  expect(broken.docScrollW, JSON.stringify(broken)).toBeGreaterThan(
    broken.docClientW + 100,
  );
});

test("document never overflows horizontally (root cause: prevents Chrome layout-viewport inflation)", async ({
  page,
  viewport,
}) => {
  expect(viewport).toBeTruthy();
  // Per the research: on Chrome Android, document.scrollWidth >
  // document.clientWidth inflates the fixed viewport to the minimum-
  // scale rect, throwing all `position: fixed` modals off-screen. The
  // ONLY robust fix is to keep document.scrollWidth ≤ clientWidth.
  // overflow-x: hidden on html/body is intentionally ignored by Chrome
  // in this scenario, so the kanban must scroll *inside* a bounded
  // container, and the column widths must use dvw (visible viewport),
  // not vw (inflated layout viewport).
  const dims = await page.evaluate(() => ({
    docScrollW: document.documentElement.scrollWidth,
    docClientW: document.documentElement.clientWidth,
    bodyScrollW: document.body.scrollWidth,
    innerW: window.innerWidth,
    vvW: window.visualViewport?.width ?? null,
  }));
  expect(dims.docScrollW, JSON.stringify(dims)).toBeLessThanOrEqual(
    dims.docClientW + 2,
  );
  expect(dims.innerW, JSON.stringify(dims)).toBeLessThanOrEqual(
    (dims.vvW ?? dims.docClientW) + 2,
  );
});

test("opened card modal lands inside the visible viewport", async ({
  page,
  viewport,
}) => {
  expect(viewport).toBeTruthy();
  const card = page.getByText("BISON-01").first();
  await card.click();
  await page.waitForTimeout(500);

  const measurement = await page.evaluate(() => {
    const dlg = document.querySelector('[role="dialog"]');
    if (!dlg) return null;
    const dlgRect = (dlg as HTMLElement).getBoundingClientRect();
    const inner = dlg.querySelector(":scope > *");
    const innerRect = inner
      ? (inner as HTMLElement).getBoundingClientRect()
      : null;
    return {
      innerW: window.innerWidth,
      innerH: window.innerHeight,
      vvW: window.visualViewport?.width ?? null,
      vvH: window.visualViewport?.height ?? null,
      dialog: { x: dlgRect.x, y: dlgRect.y, w: dlgRect.width, h: dlgRect.height },
      inner: innerRect
        ? { x: innerRect.x, y: innerRect.y, w: innerRect.width, h: innerRect.height }
        : null,
    };
  });

  expect(measurement, "dialog must be in the DOM").not.toBeNull();
  const m = measurement!;
  const vw = m.vvW ?? viewport!.width;
  const vh = m.vvH ?? viewport!.height;

  // The backdrop itself must occupy the *visible* viewport, not the
  // (possibly inflated) layout viewport. With the fix it sits at the
  // visualViewport's width/height.
  expect(m.dialog.x, JSON.stringify(m)).toBeGreaterThanOrEqual(-2);
  expect(m.dialog.y, JSON.stringify(m)).toBeGreaterThanOrEqual(-2);
  expect(m.dialog.w, JSON.stringify(m)).toBeLessThanOrEqual(vw + 4);
  expect(m.dialog.h, JSON.stringify(m)).toBeLessThanOrEqual(vh + 4);

  // The inner modal must land inside the visible viewport — the user
  // must not have to pan or pinch-zoom to find it.
  expect(m.inner, "inner modal child must exist").not.toBeNull();
  expect(m.inner!.x, JSON.stringify(m)).toBeGreaterThanOrEqual(-2);
  expect(m.inner!.x + m.inner!.w, JSON.stringify(m)).toBeLessThanOrEqual(vw + 4);
  expect(m.inner!.y, JSON.stringify(m)).toBeGreaterThanOrEqual(-2);
  expect(m.inner!.y + m.inner!.h, JSON.stringify(m)).toBeLessThanOrEqual(vh + 4);
});
