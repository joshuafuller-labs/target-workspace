// Track state machine per ukraine-fires-targeting.md §1.
//
// "Freshness" (freshness.ts) is about the LAST OBSERVATION timestamp —
// a UX hint for analyst eyes. "Track state" is a stronger semantic
// claim about the track itself: do we still believe the propagated
// position represents the contact?
//
//   active    recent observation; position trusted
//   coasting  no recent obs but still inside the lost window — UI shows
//             last-known with a "coasting" treatment so the operator
//             knows the position is propagated, not measured
//   stale     older than the freshness threshold — needs re-observation
//   lost      no observation past the lost threshold; treat as
//             potentially gone (sensor moved on, contact evaded)
//
// Thresholds are workspace-tuneable later (tw-smc follow-up). For now,
// these are sensible defaults for a tactical kill-chain pace.

import { parseIso } from "./age";

export type TrackState = "active" | "coasting" | "stale" | "lost";

const SECOND = 1000;
const MINUTE = 60 * SECOND;

const TRACK_ACTIVE_MS = 5 * MINUTE; // < 5m  -> active
const TRACK_COASTING_MS = 30 * MINUTE; // < 30m -> coasting
const TRACK_STALE_MS = 90 * MINUTE; // < 90m -> stale; otherwise lost

export interface TrackStateBucket {
  state: TrackState;
  label: string;
  /** CSS var (without `var(...)`) for the badge color. */
  colorVar: string;
  /** Display tone — used by map renderers to choose alpha / dash. */
  treatment: "solid" | "dashed" | "dim" | "crosshatch";
}

export function trackStateOf(
  observedAtIso: string,
  now: Date = new Date(),
): TrackStateBucket {
  const observed = parseIso(observedAtIso);
  const ageMs = now.getTime() - observed;

  if (ageMs < TRACK_ACTIVE_MS) {
    return {
      state: "active",
      label: "ACTIVE",
      colorVar: "--tw-accent",
      treatment: "solid",
    };
  }
  if (ageMs < TRACK_COASTING_MS) {
    return {
      state: "coasting",
      label: "COASTING",
      colorVar: "--tw-approval",
      treatment: "dashed",
    };
  }
  if (ageMs < TRACK_STALE_MS) {
    return {
      state: "stale",
      label: "STALE",
      colorVar: "--tw-ink-dim",
      treatment: "dim",
    };
  }
  return {
    state: "lost",
    label: "LOST",
    colorVar: "--tw-ink-dim",
    treatment: "crosshatch",
  };
}
