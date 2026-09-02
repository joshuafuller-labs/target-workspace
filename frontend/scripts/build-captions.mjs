#!/usr/bin/env node
/**
 * Build-captions for the animated walkthrough (tw-4ty).
 *
 * Reads a {t0, steps[]} JSON produced by walkthrough.spec.ts via
 * testInfo.attach, and emits a WebVTT file whose cues line up with
 * the recorded video.
 *
 * Each step has:
 *   { narration: string, dwell_ms: number, recorded_at_ms: number }
 *
 * recorded_at_ms is when narrate() was called, measured relative to
 * the Playwright performance origin. We subtract t0 (the page.goto
 * timestamp) so cues start at 00:00.000 from the user's perspective
 * — Playwright video begins recording at context creation, which is
 * effectively t0.
 *
 * Usage:
 *   node scripts/build-captions.mjs <steps.json> <out.vtt>
 */

import { readFileSync, writeFileSync } from "node:fs";

const [, , stepsPath, vttPath] = process.argv;
if (!stepsPath || !vttPath) {
  console.error("usage: build-captions.mjs <steps.json> <out.vtt>");
  process.exit(2);
}

const { t0, steps } = JSON.parse(readFileSync(stepsPath, "utf8"));

function fmtTimestamp(ms) {
  const total = Math.max(0, Math.round(ms));
  const h = Math.floor(total / 3_600_000);
  const m = Math.floor((total % 3_600_000) / 60_000);
  const s = Math.floor((total % 60_000) / 1_000);
  const r = total % 1_000;
  const pad = (n, w = 2) => String(n).padStart(w, "0");
  return `${pad(h)}:${pad(m)}:${pad(s)}.${pad(r, 3)}`;
}

const lines = ["WEBVTT", "", "NOTE", "Generated from walkthrough.spec.ts (tw-4ty).", ""];

let cueIdx = 1;
for (const step of steps) {
  const startMs = Math.max(0, step.recorded_at_ms - t0);
  const endMs = startMs + step.dwell_ms;
  lines.push(String(cueIdx));
  lines.push(`${fmtTimestamp(startMs)} --> ${fmtTimestamp(endMs)}`);
  lines.push(step.narration);
  lines.push("");
  cueIdx += 1;
}

writeFileSync(vttPath, lines.join("\n"), "utf8");
console.log(`[build-captions] wrote ${cueIdx - 1} cues to ${vttPath}`);
