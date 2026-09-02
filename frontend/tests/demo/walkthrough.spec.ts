import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect, type Page } from "@playwright/test";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Animated walkthrough recording (tw-4ty).
 *
 * Story arc — Kerr County flash flood, the disaster scenario seeded
 * by docker-compose. Drives a feature-rich tour:
 *
 *   1. Cold open on the Incident Response · Op Period 1 board with
 *      all 5 columns populated.
 *   2. Pause on the kanban density — 16 cards spanning welfare
 *      checks, hazards, SAR tasks, resources, in-progress rescues.
 *   3. Open MISSING-001 (the dedup of WC-MISSING-001a/b) and linger
 *      on TargetDetail — audit chain, observations, live positions.
 *   4. Switch boards via the header picker.
 *   5. /audit — filter by event type, export CSV.
 *   6. /settings — General tab, brand name input.
 *   7. End.
 *
 * Caption cues are recorded as we go; build-captions.mjs walks them
 * into a VTT, and record-demo.sh burns the VTT onto the video via
 * the ffmpeg subtitles filter.
 */

const ADMIN_EMAIL = "admin@example.com";
const ADMIN_PASSWORD = "demopw";
const KERR_BOARD = "Incident Response · Op Period 1";

interface Step {
  narration: string;
  dwell_ms: number;
  recorded_at_ms?: number;
}
const steps: Step[] = [];

async function narrate(
  page: Page,
  narration: string,
  dwell_ms: number,
): Promise<void> {
  steps.push({
    narration,
    dwell_ms,
    recorded_at_ms: Math.round(performance.now()),
  });
  await page.waitForTimeout(dwell_ms);
}

test("animated walkthrough — Kerr County disaster", async ({ page }) => {
  page.on("pageerror", (err) => {
    // eslint-disable-next-line no-console
    console.log("[browser-pageerror]", err.message);
  });

  const t0 = performance.now();
  await page.goto("/");
  await page.waitForLoadState("networkidle").catch(() => undefined);

  // ── Login ─────────────────────────────────────────────────────────
  await page.locator("#login-identifier").waitFor({ state: "visible", timeout: 15_000 });
  await page.locator("#login-identifier").fill(ADMIN_EMAIL);
  await page.locator("#password").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: /sign in|log in/i }).click();
  await expect(page.locator("body")).toContainText(/board/i, { timeout: 15_000 });
  await page.waitForLoadState("networkidle").catch(() => undefined);

  // Dismiss the onboarding hint silently so it doesn't sit through
  // the entire recording.
  const dismiss = page.getByRole("button", { name: /dismiss tip/i });
  if (await dismiss.isVisible().catch(() => false)) {
    await dismiss.click();
    await page.waitForTimeout(300);
  }

  // ── Cold open ─────────────────────────────────────────────────────
  // Switch to the Kerr County board via the header picker.
  await selectBoard(page, KERR_BOARD);
  await narrate(
    page,
    "Kerr County, Texas. Guadalupe River at flood stage. The operations cell is running this incident through Target Workspace.",
    4_500,
  );

  // Pan a beat across the kanban — let the viewer see the volume.
  await page.mouse.move(960, 540);
  await narrate(
    page,
    "Sixteen cards across five columns — welfare checks, hazards, SAR tasks, and the resources that handle them.",
    5_000,
  );

  // Highlight the hazard treatment by scrolling its card into view.
  const hazardCard = page
    .getByRole("button")
    .filter({ hasText: /HAZARD-LWX-2207-MARKED|311-LWX-2207|DEP-OBS-118/ })
    .first();
  if (await hazardCard.isVisible().catch(() => false)) {
    await hazardCard.scrollIntoViewIfNeeded().catch(() => undefined);
    await page.waitForTimeout(800);
    await narrate(
      page,
      "Hazards render in warning red — flooded crossings, debris piles, gas leaks — distinct from contacts on both the card and the map.",
      4_500,
    );
  }

  // ── TargetDetail — the marquee feature ───────────────────────────
  const missingCard = page
    .getByRole("button")
    .filter({ hasText: /^MISSING-001\b/ })
    .first();
  if (await missingCard.isVisible().catch(() => false)) {
    await missingCard.scrollIntoViewIfNeeded().catch(() => undefined);
    await page.waitForTimeout(500);
    await missingCard.click();
  } else {
    // Fallback to any card if the seed naming drifts.
    await page.getByRole("button").filter({ hasText: /^(WC|MISSING|RESCUE|SAR)/ }).first().click();
  }
  await page.waitForTimeout(1_200);
  await narrate(
    page,
    "Two family members reported the same missing girl. Track correlation merged them into one canonical target — the audit chain records both intake events.",
    6_000,
  );

  // Scroll the modal so Observations + Live Positions land in frame.
  await page.mouse.wheel(0, 400);
  await narrate(
    page,
    "Every observation that touches this target lands in the timeline — source, position, confidence. Independent cues fuse via the 1 − ∏(1 − cᵢ) rule.",
    5_500,
  );

  await page.mouse.wheel(0, 400);
  await narrate(
    page,
    "Live positions of assigned callsigns — distance, bearing, speed. PLI from TAK Server. Geofence-arrival auto-promotes the card when the team is on-scene.",
    5_500,
  );

  // Close the modal.
  await page.keyboard.press("Escape");
  await page.waitForTimeout(600);

  // ── Audit log ─────────────────────────────────────────────────────
  await page.goto("/audit");
  await expect(page.getByRole("heading", { name: /Audit Log/i })).toBeVisible({
    timeout: 5_000,
  });
  await page.waitForTimeout(600);
  await narrate(
    page,
    "Every state change writes a signed, append-only audit event. Filter by actor, event type, time window, or full-text.",
    4_500,
  );

  const filterInput = page.getByPlaceholder(/event_type/i);
  if (await filterInput.isVisible().catch(() => false)) {
    // Backend filters event_type exactly; use the canonical success
    // type so the table populates with real rows.
    await filterInput.fill("auth.login.success");
    await page.waitForTimeout(2_000);
  }
  await narrate(
    page,
    "Export to CSV for after-action review, FOIA response, or chain-of-custody attestation.",
    4_500,
  );

  // ── Settings ──────────────────────────────────────────────────────
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: /^Settings$/i })).toBeVisible({
    timeout: 5_000,
  });
  await page.waitForTimeout(800);
  await narrate(
    page,
    "Workspace settings are per-tenant — brand, theme, freshness window, correlation tolerance. Admins edit inline; no rebuild required.",
    5_000,
  );

  // ── Close ─────────────────────────────────────────────────────────
  await page.goto("/");
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(800);
  await narrate(
    page,
    "Target Workspace — CoT-native, configurable, audit-grade. Built for the ops cell that takes the call.",
    5_500,
  );

  // Persist the timing log into docs/demo/ where the caption builder
  // expects it. __dirname is frontend/tests/demo, three levels up is
  // the repo root.
  const stepsDir = path.resolve(__dirname, "../../../docs/demo");
  mkdirSync(stepsDir, { recursive: true });
  writeFileSync(
    path.join(stepsDir, "walkthrough-steps.json"),
    JSON.stringify({ t0, steps }, null, 2),
  );
});

/**
 * Switch boards via the header <select> (aria-label="Switch board").
 * The select only renders when allBoards.length > 1.
 */
async function selectBoard(page: Page, boardName: string): Promise<void> {
  const picker = page.getByLabel("Switch board");
  if (!(await picker.isVisible().catch(() => false))) {
    return; // single-board workspace; nothing to switch
  }
  await picker.selectOption({ label: boardName });
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(800);
}
