// Backfill tests for the age counter (tw-ced). Pure-function coverage
// of the m:ss / h:mm:ss / Nd formatter, the freshness-bucket → color
// mapping, and the missing-tz parseIso defense.
//
// Per TDD audit step 4 these were written against the shipped impl
// AND verified to fail when key constants are mutated — the harness
// at scripts/audit/mutation_audit.py is the regression net.

import { describe, expect, it } from "vitest";

import { ageDisplay, formatAge, parseIso } from "./age";

describe("formatAge", () => {
  it("< 1 minute renders 0:SS with seconds zero-padded", () => {
    expect(formatAge(0)).toBe("0:00");
    expect(formatAge(1_000)).toBe("0:01");
    expect(formatAge(7_000)).toBe("0:07");
    expect(formatAge(59_999)).toBe("0:59");
  });

  it("minutes between 1 and 59 render m:ss", () => {
    expect(formatAge(60_000)).toBe("1:00");
    expect(formatAge(60_000 + 7_000)).toBe("1:07");
    expect(formatAge(47 * 60_000)).toBe("47:00");
    expect(formatAge(59 * 60_000 + 59_000)).toBe("59:59");
  });

  it("≥ 1 hour switches to h:mm:ss with both fields zero-padded", () => {
    expect(formatAge(60 * 60_000)).toBe("1:00:00");
    expect(formatAge(60 * 60_000 + 7 * 60_000 + 3_000)).toBe("1:07:03");
    expect(formatAge(2 * 60 * 60_000 + 14 * 60_000 + 8_000)).toBe("2:14:08");
  });

  it("≥ 1 day collapses to Nd (we don't carry hours past day boundary)", () => {
    expect(formatAge(24 * 60 * 60_000)).toBe("1d");
    expect(formatAge(48 * 60 * 60_000 + 5 * 60_000)).toBe("2d");
  });

  it("negative age clamps to 0 (prevents counter going backward when clock skew)", () => {
    // The shipped clamp is the linchpin that broke during the TZ bug —
    // a US-east browser saw all timestamps in the future and clamped to
    // 0:00, hiding the real issue. The clamp itself is correct
    // behaviour (we never want to render "−4:19"); the TZ fix is
    // verified separately. Here we just assert the clamp.
    expect(formatAge(-5_000)).toBe("0:00");
    expect(formatAge(-60 * 60_000)).toBe("0:00");
  });
});

describe("parseIso", () => {
  // Per ECMA spec, new Date("2026-05-17T14:35:17") with no tz suffix
  // is parsed as LOCAL time. Our backend now emits Z, but parseIso is
  // the belt-and-suspenders defense — naive datetime strings must be
  // coerced to UTC before constructing the Date.
  it("string with Z suffix parses as UTC", () => {
    const ms = parseIso("2026-05-17T14:35:17Z");
    expect(ms).toBe(Date.UTC(2026, 4, 17, 14, 35, 17));
  });

  it("string with +HH:MM offset parses correctly", () => {
    const ms = parseIso("2026-05-17T14:35:17+00:00");
    expect(ms).toBe(Date.UTC(2026, 4, 17, 14, 35, 17));
  });

  it("string with NO timezone suffix is treated as UTC (defense)", () => {
    const ms = parseIso("2026-05-17T14:35:17.686298");
    // Same wall-clock value as the Z-suffixed equivalent.
    expect(ms).toBe(Date.UTC(2026, 4, 17, 14, 35, 17, 686));
  });

  it("naive vs Z-suffixed strings of the same moment yield the same epoch ms", () => {
    expect(parseIso("2026-05-17T14:35:17")).toBe(
      parseIso("2026-05-17T14:35:17Z"),
    );
  });
});

describe("ageDisplay", () => {
  const obs = "2026-05-17T12:00:00Z";
  const now = (offsetMs: number) =>
    new Date(Date.UTC(2026, 4, 17, 12, 0, 0) + offsetMs).getTime();

  it("freshly-observed (< 60s) lands in `live` bucket with accent color", () => {
    const r = ageDisplay(obs, now(30_000));
    expect(r.bucket).toBe("live");
    expect(r.colorVar).toBe("--tw-accent");
    expect(r.text).toBe("0:30");
  });

  it("1-5 minute window lands in `recent` bucket (still accent)", () => {
    const r = ageDisplay(obs, now(3 * 60_000 + 14_000));
    expect(r.bucket).toBe("recent");
    expect(r.colorVar).toBe("--tw-accent");
    expect(r.text).toBe("3:14");
  });

  it("5-15 minute window lands in `warm` bucket (approval color)", () => {
    const r = ageDisplay(obs, now(10 * 60_000));
    expect(r.bucket).toBe("warm");
    expect(r.colorVar).toBe("--tw-approval");
  });

  it("≥ 15 min lands in `stale` bucket (dim color)", () => {
    const r = ageDisplay(obs, now(45 * 60_000));
    expect(r.bucket).toBe("stale");
    expect(r.colorVar).toBe("--tw-ink-dim");
    expect(r.text).toBe("45:00");
  });

  it("naive-tz timestamp is treated as UTC (regression test for the 0:00 bug)", () => {
    // The shipped TZ bug made US-east browsers see all targets in the
    // future and clamp to 0:00. parseIso defends; ageDisplay routes
    // through it. If parseIso ever stops defending, this test fails
    // because the naive string would be read as local time → ageMs
    // becomes negative on a non-UTC test runner.
    const r = ageDisplay("2026-05-17T12:00:00", now(30 * 60_000));
    expect(r.bucket).toBe("stale");
    expect(r.text).toBe("30:00");
  });
});
