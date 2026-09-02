// Target search/filter parser + matcher.
//
// Query syntax — whitespace-separated terms, all ANDed. Bare terms match
// substring on name or source. Prefixed terms scope to one field:
//
//   bison                    -> name|source contains "bison"
//   cot:a-h-G                -> cot_type starts with "a-h-G"
//   src:RQ-7                 -> source contains "RQ-7"
//   name:BISON-01            -> name contains "BISON-01"
//   qual:confirmed           -> geometry_quality === "confirmed"
//   fresh:live               -> freshness bucket === "live"
//
// Cards that don't match fade rather than vanish, so spatial intuition
// (where in the column the card lives) is preserved — per the tw-t4h
// requirement.

import { freshnessOf, type Freshness } from "./freshness";
import { trackStateOf, type TrackState } from "./track_state";
import type { GeometryQuality, Target } from "./types";

interface Term {
  field: "free" | "cot" | "name" | "src" | "qual" | "fresh" | "track";
  value: string;
}

export interface FilterSpec {
  raw: string;
  terms: Term[];
}

export const EMPTY_FILTER: FilterSpec = { raw: "", terms: [] };

export function parseQuery(raw: string): FilterSpec {
  const trimmed = raw.trim();
  if (!trimmed) return { raw, terms: [] };
  const tokens = trimmed.split(/\s+/);
  const terms: Term[] = [];
  for (const tok of tokens) {
    const colon = tok.indexOf(":");
    if (colon > 0) {
      const field = tok.slice(0, colon).toLowerCase();
      const value = tok.slice(colon + 1).toLowerCase();
      if (
        field === "cot" ||
        field === "name" ||
        field === "src" ||
        field === "qual" ||
        field === "fresh" ||
        field === "track"
      ) {
        if (value) terms.push({ field, value });
        continue;
      }
    }
    terms.push({ field: "free", value: tok.toLowerCase() });
  }
  return { raw, terms };
}

/** Check whether a target matches every term in the filter. Empty
 *  filter matches everything (returns `true`).
 *
 *  Pass `now` to keep freshness calculations stable across a render
 *  pass (otherwise tests that bucket "edge" cases flake). */
export function matchesTarget(
  target: Target,
  spec: FilterSpec,
  now: Date = new Date(),
): boolean {
  if (spec.terms.length === 0) return true;
  const name = target.name.toLowerCase();
  const cot = target.cot_type.toLowerCase();
  const src = (target.source ?? "").toLowerCase();
  let freshKind: Freshness | null = null;
  let trackKind: TrackState | null = null;
  let qual: GeometryQuality | null = null;
  for (const t of spec.terms) {
    switch (t.field) {
      case "free":
        if (!name.includes(t.value) && !src.includes(t.value)) return false;
        break;
      case "name":
        if (!name.includes(t.value)) return false;
        break;
      case "src":
        if (!src.includes(t.value)) return false;
        break;
      case "cot":
        if (!cot.startsWith(t.value)) return false;
        break;
      case "qual":
        if (!qual) qual = target.geometry_quality;
        if (qual !== t.value) return false;
        break;
      case "fresh":
        if (!freshKind) freshKind = freshnessOf(target.time, now).kind;
        if (freshKind !== t.value) return false;
        break;
      case "track":
        if (!trackKind) trackKind = trackStateOf(target.time, now).state;
        if (trackKind !== t.value) return false;
        break;
    }
  }
  return true;
}
