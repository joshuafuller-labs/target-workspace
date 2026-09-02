/**
 * Viewport matrix per ADR 0011 (tw-y60).
 *
 * Runs the shared overflow / overlap / tap-target contracts across
 * the six canonical viewports (project config sets each viewport):
 *
 *   360x800   — small phone (Samsung Galaxy class)
 *   412x915   — medium phone (Pixel 7 class)
 *   720x1024  — small tablet portrait
 *   1024x720  — small tablet landscape
 *   1440x900  — laptop
 *   1920x1080 — desktop
 *
 * Each project name selects only this file, so per-viewport assertion
 * runs as its own test instance with the right viewport baked in.
 */

import { expect, test } from "@playwright/test";

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

test("document does not overflow horizontally", async ({ page, viewport }) => {
  expect(viewport).toBeTruthy();
  const dims = await page.evaluate(() => ({
    docClientW: document.documentElement.clientWidth,
    bodyScrollW: document.body.scrollWidth,
  }));
  // Allow tiny rounding (≤4px) — Chrome can report sub-pixel rects.
  expect(dims.bodyScrollW, JSON.stringify(dims)).toBeLessThanOrEqual(
    dims.docClientW + 4,
  );
});

test("no app-owned interactive element is < 40px on both dimensions", async ({
  page,
}) => {
  const tiny = await page.evaluate(() => {
    const out: { tag: string; w: number; h: number; text: string }[] = [];
    const all = document.querySelectorAll(
      "button, a, input, select, textarea, [role='button']",
    );
    for (const el of all) {
      // Skip Cesium's own controls — not our markup.
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
  expect(tiny, JSON.stringify(tiny, null, 2)).toEqual([]);
});

test("no two siblings overlap horizontally inside the header", async ({
  page,
}) => {
  // Detects cases where the header items pack too tightly and visually
  // collide on a given viewport.
  const overlaps = await page.evaluate(() => {
    const header = document.querySelector("header");
    if (!header) return [];
    const kids = Array.from(header.children) as HTMLElement[];
    const rects = kids.map((k) => k.getBoundingClientRect());
    const out: { a: string; b: string }[] = [];
    for (let i = 0; i < rects.length; i++) {
      for (let j = i + 1; j < rects.length; j++) {
        const a = rects[i];
        const b = rects[j];
        // Skip elements that are stacked vertically (different rows).
        if (a.bottom <= b.top || b.bottom <= a.top) continue;
        // Overlap when their horizontal ranges intersect by more than 1px.
        const overlap = Math.min(a.right, b.right) - Math.max(a.left, b.left);
        if (overlap > 1) {
          out.push({
            a: kids[i].tagName,
            b: kids[j].tagName,
          });
        }
      }
    }
    return out;
  });
  expect(overlaps, JSON.stringify(overlaps, null, 2)).toEqual([]);
});

test("header height ≤ 30% of viewport height", async ({ page, viewport }) => {
  expect(viewport).toBeTruthy();
  const h = await page.evaluate(() => {
    const header = document.querySelector("header");
    return header ? (header as HTMLElement).getBoundingClientRect().height : 0;
  });
  const cap = viewport!.height * 0.3;
  expect(h, `header ${h}px > ${cap}px`).toBeLessThanOrEqual(cap);
});
