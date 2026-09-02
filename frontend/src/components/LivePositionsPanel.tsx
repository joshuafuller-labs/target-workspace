import React from "react";
import { useEffect, useState } from "react";

import { api } from "../api";

interface Props {
  callsigns: string[];
  targetLat: number;
  targetLon: number;
}

interface Snapshot {
  callsign: string;
  lat: number;
  lon: number;
  course: number | null;
  speed: number | null;
  time: string;
  source: string | null;
}

type EntryState =
  | { kind: "loading" }
  | { kind: "online"; snap: Snapshot }
  | { kind: "offline" };

const REFRESH_MS = 10_000;

function haversineM(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number {
  const r = 6_371_000;
  const p1 = (lat1 * Math.PI) / 180;
  const p2 = (lat2 * Math.PI) / 180;
  const dp = ((lat2 - lat1) * Math.PI) / 180;
  const dl = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dp / 2) ** 2 +
    Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(a));
}

function bearingDeg(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number {
  const p1 = (lat1 * Math.PI) / 180;
  const p2 = (lat2 * Math.PI) / 180;
  const dl = ((lon2 - lon1) * Math.PI) / 180;
  const y = Math.sin(dl) * Math.cos(p2);
  const x =
    Math.cos(p1) * Math.sin(p2) -
    Math.sin(p1) * Math.cos(p2) * Math.cos(dl);
  const brng = (Math.atan2(y, x) * 180) / Math.PI;
  return (brng + 360) % 360;
}

function cardinal(deg: number): string {
  const dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
  return dirs[Math.round(deg / 45) % 8];
}

function fmtDistance(m: number): string {
  if (m < 1000) return `${Math.round(m)} m`;
  return `${(m / 1000).toFixed(1)} km`;
}

/** Live positions of the assignees on a target (tw-gaf4).
 *
 *  Polls /v1/presence/<callsign> every REFRESH_MS for each assignee.
 *  Future: subscribe to presence.update via the realtime WS instead
 *  of polling.
 */
export function LivePositionsPanel({
  callsigns,
  targetLat,
  targetLon,
}: Props): React.JSX.Element | null {
  const [entries, setEntries] = useState<Record<string, EntryState>>({});

  useEffect(() => {
    if (callsigns.length === 0) return;
    let cancelled = false;

    async function tick(): Promise<void> {
      const next: Record<string, EntryState> = {};
      await Promise.all(
        callsigns.map(async (cs) => {
          try {
            const snap = (await api.getPresence(cs)) as Snapshot;
            next[cs] = { kind: "online", snap };
          } catch {
            next[cs] = { kind: "offline" };
          }
        }),
      );
      if (!cancelled) setEntries(next);
    }

    void tick();
    const handle = window.setInterval(() => void tick(), REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, [callsigns]);

  if (callsigns.length === 0) return null;

  return (
    <section className="border-t pt-4" style={{ borderColor: "var(--tw-border)" }}>
      <p
        className="tw-eyebrow text-[10px] mb-2"
        style={{ color: "var(--tw-ink-muted)" }}
      >
        Live positions ({callsigns.length})
      </p>
      <ul className="space-y-1.5">
        {callsigns.map((cs) => {
          const e = entries[cs] ?? { kind: "loading" };
          return (
            <li
              key={cs}
              className="text-xs p-2"
              style={{
                borderWidth: 1,
                borderStyle: "solid",
                borderColor: "var(--tw-border)",
                borderRadius: "var(--tw-radius)",
                fontFamily: "var(--tw-font-mono)",
                background: "var(--tw-bg-panel)",
              }}
            >
              <div className="flex justify-between">
                <span style={{ color: "var(--tw-accent)" }}>{cs}</span>
                {e.kind === "online" && (
                  <span style={{ color: "var(--tw-ink-dim)" }}>
                    {new Date(e.snap.time).toLocaleTimeString()}
                  </span>
                )}
                {e.kind === "offline" && (
                  <span style={{ color: "var(--tw-ink-dim)" }}>offline</span>
                )}
                {e.kind === "loading" && (
                  <span style={{ color: "var(--tw-ink-dim)" }}>…</span>
                )}
              </div>
              {e.kind === "online" && (
                <div className="mt-1" style={{ color: "var(--tw-ink-muted)" }}>
                  {fmtDistance(
                    haversineM(targetLat, targetLon, e.snap.lat, e.snap.lon),
                  )}{" "}
                  {cardinal(
                    bearingDeg(e.snap.lat, e.snap.lon, targetLat, targetLon),
                  )}
                  {e.snap.speed !== null && (
                    <> · {e.snap.speed.toFixed(1)} m/s</>
                  )}
                  {e.snap.course !== null && (
                    <> · hdg {Math.round(e.snap.course)}°</>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
