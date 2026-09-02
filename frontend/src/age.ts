// Live age formatter — drives the ticking counter on every target card.
//
// Format choice: m:ss until 1 hour, then h:mm:ss. This matches how
// operators say durations out loud ("two-thirty since contact",
// "one-fourteen-oh-eight"), and the tighter format keeps card real
// estate stable as ages grow.
//
// Color thresholds re-use the freshness palette so the visual reading
// stays consistent with track-state and the filter chips.

import type { Freshness } from "./freshness";

const SECOND = 1000;
const MINUTE = 60 * SECOND;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

const FRESHNESS_RECENT = 60 * SECOND; // < 60s
const FRESHNESS_WARM = 5 * MINUTE; // < 5m
const FRESHNESS_STALE = 15 * MINUTE; // < 15m  -> warm; otherwise stale

export interface AgeDisplay {
  /** Formatted text, e.g. "0:47" / "3:21" / "1:14:08" / "2d". */
  text: string;
  /** Freshness bucket — used for color + filter integration. */
  bucket: Freshness;
  /** CSS var name (without var(...)) for the counter color. */
  colorVar: string;
}

/** Format milliseconds-since-observation into a stable-width string. */
export function formatAge(ageMs: number): string {
  if (ageMs < 0) ageMs = 0;
  if (ageMs >= DAY) {
    const days = Math.floor(ageMs / DAY);
    return `${days}d`;
  }
  const totalSec = Math.floor(ageMs / SECOND);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  if (h > 0) {
    return `${h}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  }
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** Parse an ISO 8601 datetime, defaulting to UTC if no timezone marker
 *  is present. JS Date() spec says naive datetime → local time, which
 *  breaks the counter for any non-UTC browser when the server has been
 *  sloppy about emitting Z. We fix the server (tw-qt6) but defend here
 *  so a future regression doesn't silently zero every counter. */
export function parseIso(iso: string): number {
  // Detect a timezone suffix: Z, +HH:MM, +HHMM, -HH:MM, or -HHMM.
  const hasTz = /(Z|[+-]\d{2}:?\d{2})$/.test(iso);
  return new Date(hasTz ? iso : iso + "Z").getTime();
}

/** Bucket + color for a given age. Same thresholds as freshness.ts —
 *  centralized here for the counter so the LIVE/recent/warm/stale text
 *  labels don't have to follow. */
export function ageDisplay(observedAtIso: string, now: number): AgeDisplay {
  const observed = parseIso(observedAtIso);
  const ageMs = now - observed;
  let bucket: Freshness;
  let colorVar: string;
  if (ageMs < FRESHNESS_RECENT) {
    bucket = "live";
    colorVar = "--tw-accent";
  } else if (ageMs < FRESHNESS_WARM) {
    bucket = "recent";
    colorVar = "--tw-accent";
  } else if (ageMs < FRESHNESS_STALE) {
    bucket = "warm";
    colorVar = "--tw-approval";
  } else {
    bucket = "stale";
    colorVar = "--tw-ink-dim";
  }
  return { text: formatAge(ageMs), bucket, colorVar };
}
