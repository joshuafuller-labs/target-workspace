// Time-since-observed buckets per docs/research/ukraine-fires-targeting.md §1.
//
// Display of per-target age lives in age.ts (ticking counter, see tw-ced).
// This module is now used only for:
//   - the `fresh:` filter prefix (parses bucket names),
//   - the map alpha tier in MapPane (re-uses the same boundaries).
//
// Thresholds are workspace-tuneable later (tw-smc follow-up).

import { parseIso } from "./age";

export type Freshness = "live" | "recent" | "warm" | "stale";

export interface FreshnessBucket {
  kind: Freshness;
  /** CSS var name (without `var(...)`) for the dot color. */
  colorVar: string;
}

const MINUTE = 60 * 1000;

const THRESHOLD_LIVE_MS = MINUTE; // < 1m
const THRESHOLD_RECENT_MS = 5 * MINUTE; // < 5m
const THRESHOLD_WARM_MS = 15 * MINUTE; // < 15m

/** Bucket a target's observation time into a freshness bucket + color. */
export function freshnessOf(observedAtIso: string, now: Date = new Date()): FreshnessBucket {
  const observed = parseIso(observedAtIso);
  const ageMs = now.getTime() - observed;
  if (ageMs < THRESHOLD_LIVE_MS) return { kind: "live", colorVar: "--tw-accent" };
  if (ageMs < THRESHOLD_RECENT_MS) return { kind: "recent", colorVar: "--tw-accent" };
  if (ageMs < THRESHOLD_WARM_MS) return { kind: "warm", colorVar: "--tw-approval" };
  return { kind: "stale", colorVar: "--tw-ink-dim" };
}
