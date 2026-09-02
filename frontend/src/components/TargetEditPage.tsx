import React from "react";
import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import { navigate } from "../router";
import type { AuditEventOut, Target, TargetUpdatePayload, UserOut } from "../types";
import { CotTypePicker } from "./CotTypePicker";

interface Props {
  user: UserOut;
  targetId: string;
}

/** Full-page target editor — deep-linkable at `/targets/:id/edit`.
 *
 *  The TargetDetail modal stays for inline preview from the kanban.
 *  This page is for "I need to actually work this contact for 60s":
 *  mobile-first single column, generous tap targets, sections expanded
 *  by default, all fields persisted via PATCH-on-blur. */
export function TargetEditPage({ user: _user, targetId }: Props): React.JSX.Element {
  const [target, setTarget] = useState<Target | null>(null);
  const [events, setEvents] = useState<AuditEventOut[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Editable state — mirrors target fields, flushed on blur.
  const [name, setName] = useState("");
  const [cotType, setCotType] = useState("");
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [hae, setHae] = useState("");
  const [ce, setCe] = useState("");
  const [le, setLe] = useState("");
  const [confidence, setConfidence] = useState("");
  const [source, setSource] = useState("");
  const [remarks, setRemarks] = useState("");

  const savedRef = useRef<Target | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const t = await api.getTarget(targetId);
        if (cancelled) return;
        setTarget(t);
        savedRef.current = t;
        setName(t.name);
        setCotType(t.cot_type);
        setLat(String(t.lat));
        setLon(String(t.lon));
        setHae(t.hae == null ? "" : String(t.hae));
        setCe(t.ce == null ? "" : String(t.ce));
        setLe(t.le == null ? "" : String(t.le));
        setConfidence(t.confidence == null ? "" : String(t.confidence));
        setSource(t.source ?? "");
        setRemarks(t.remarks ?? "");
        const audit = await api.listAudit(t.id);
        if (!cancelled) setEvents(audit);
      } catch (err) {
        if (!cancelled) setError(String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [targetId]);

  async function patch(payload: TargetUpdatePayload): Promise<void> {
    setError(null);
    try {
      const updated = await api.updateTarget(targetId, payload);
      setTarget(updated);
      savedRef.current = updated;
      setEvents(await api.listAudit(updated.id));
    } catch (err) {
      setError(String(err));
    }
  }

  function flushIfChanged<K extends keyof TargetUpdatePayload>(
    key: K,
    value: TargetUpdatePayload[K],
    pre: TargetUpdatePayload[K],
  ): void {
    if (value === pre) return;
    void patch({ [key]: value } as TargetUpdatePayload);
  }

  function flushNumber(
    key: "confidence" | "hae" | "ce" | "le",
    text: string,
  ): void {
    if (!savedRef.current) return;
    const pre = savedRef.current[key];
    const next = text.trim() === "" ? null : Number(text);
    if (next !== null && Number.isNaN(next)) return;
    if (next === pre) return;
    void patch({ [key]: next } as TargetUpdatePayload);
  }

  function flushCoord(key: "lat" | "lon", text: string): void {
    if (!savedRef.current) return;
    const pre = savedRef.current[key];
    const next = Number(text);
    if (!Number.isFinite(next)) return;
    if (next === pre) return;
    void patch({ [key]: next } as TargetUpdatePayload);
  }

  function backToBoard(): void {
    navigate("/");
  }

  if (!target) {
    return (
      <main
        className="min-h-screen flex items-center justify-center"
        style={{ background: "var(--tw-bg)", color: "var(--tw-ink-muted)" }}
      >
        <p className="text-sm">{error ?? "Loading target…"}</p>
      </main>
    );
  }

  return (
    <main
      className="min-h-screen pb-12"
      style={{ background: "var(--tw-bg)", color: "var(--tw-ink)" }}
    >
      <header
        className="tw-rail px-4 desktop:px-6 py-3 border-b sticky top-0 z-20 flex items-center gap-3"
        style={{
          background: "var(--tw-bg-panel)",
          borderColor: "var(--tw-border)",
        }}
      >
        <button
          onClick={backToBoard}
          className="tw-eyebrow text-[11px] px-3"
          style={{
            background: "transparent",
            borderWidth: 1,
            borderStyle: "solid",
            borderColor: "var(--tw-border)",
            borderRadius: "var(--tw-radius)",
            color: "var(--tw-ink-muted)",
            minHeight: 44,
          }}
          aria-label="Back to board"
        >
          ← Board
        </button>
        <div className="flex-1 min-w-0">
          <p
            className="tw-eyebrow text-[10px]"
            style={{ color: "var(--tw-brand)" }}
          >
            Editing target
          </p>
          <h1
            className="tw-display text-lg desktop:text-xl truncate"
            style={{ color: "var(--tw-ink)" }}
          >
            {target.name}
          </h1>
        </div>
        <code
          className="hidden desktop:block text-[10px]"
          style={{
            color: "var(--tw-ink-dim)",
            fontFamily: "var(--tw-font-mono)",
          }}
        >
          v{target.version}
        </code>
      </header>

      {error && (
        <div
          className="mx-4 desktop:mx-6 mt-4 px-3 py-2 text-sm"
          style={{
            background: "var(--tw-bg-panel)",
            borderLeftWidth: 3,
            borderLeftStyle: "solid",
            borderLeftColor: "var(--tw-approval)",
            color: "var(--tw-approval)",
          }}
        >
          {error}
        </div>
      )}

      <div className="max-w-3xl mx-auto px-4 desktop:px-6 space-y-6 pt-4">
        <Section title="Identity" hint="Callsign and CoT classification.">
          <Labeled label="Callsign" id="t-name">
            <input
              id="t-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onBlur={() =>
                flushIfChanged("name", name, savedRef.current?.name)
              }
              className="w-full px-3 py-2"
              style={inputStyle}
            />
          </Labeled>
          <div className="space-y-2">
            <p
              className="tw-eyebrow text-[10px]"
              style={{ color: "var(--tw-ink-dim)" }}
            >
              CoT type
            </p>
            <CotTypePicker
              value={cotType}
              onChange={(next) => {
                setCotType(next);
                if (next !== savedRef.current?.cot_type) {
                  void patch({ cot_type: next });
                }
              }}
            />
          </div>
        </Section>

        <Section title="Geometry" hint="Position and uncertainty.">
          <div className="grid grid-cols-2 gap-3">
            <Labeled label="Latitude" id="t-lat">
              <input
                id="t-lat"
                value={lat}
                inputMode="decimal"
                onChange={(e) => setLat(e.target.value)}
                onBlur={() => flushCoord("lat", lat)}
                className="w-full px-3 py-2"
                style={{ ...inputStyle, fontFamily: "var(--tw-font-mono)" }}
              />
            </Labeled>
            <Labeled label="Longitude" id="t-lon">
              <input
                id="t-lon"
                value={lon}
                inputMode="decimal"
                onChange={(e) => setLon(e.target.value)}
                onBlur={() => flushCoord("lon", lon)}
                className="w-full px-3 py-2"
                style={{ ...inputStyle, fontFamily: "var(--tw-font-mono)" }}
              />
            </Labeled>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <Labeled label="HAE (m)" id="t-hae">
              <input
                id="t-hae"
                value={hae}
                inputMode="decimal"
                onChange={(e) => setHae(e.target.value)}
                onBlur={() => flushNumber("hae", hae)}
                className="w-full px-3 py-2"
                style={{ ...inputStyle, fontFamily: "var(--tw-font-mono)" }}
              />
            </Labeled>
            <Labeled label="CE (m)" id="t-ce">
              <input
                id="t-ce"
                value={ce}
                inputMode="decimal"
                onChange={(e) => setCe(e.target.value)}
                onBlur={() => flushNumber("ce", ce)}
                className="w-full px-3 py-2"
                style={{ ...inputStyle, fontFamily: "var(--tw-font-mono)" }}
              />
            </Labeled>
            <Labeled label="LE (m)" id="t-le">
              <input
                id="t-le"
                value={le}
                inputMode="decimal"
                onChange={(e) => setLe(e.target.value)}
                onBlur={() => flushNumber("le", le)}
                className="w-full px-3 py-2"
                style={{ ...inputStyle, fontFamily: "var(--tw-font-mono)" }}
              />
            </Labeled>
          </div>
          <Labeled label="Confidence (0-1)" id="t-conf">
            <input
              id="t-conf"
              value={confidence}
              inputMode="decimal"
              onChange={(e) => setConfidence(e.target.value)}
              onBlur={() => flushNumber("confidence", confidence)}
              className="w-full px-3 py-2"
              style={{ ...inputStyle, fontFamily: "var(--tw-font-mono)" }}
            />
          </Labeled>
          <p className="text-[11px]" style={{ color: "var(--tw-ink-dim)" }}>
            Geometry kind: <strong>{target.geometry_kind}</strong> · Quality:{" "}
            <strong>{target.geometry_quality}</strong>. Drag-to-edit
            position and ellipse/polygon editing land with tw-xj4.
          </p>
        </Section>

        <Section title="Attribution" hint="Where this contact came from.">
          <Labeled label="Source" id="t-source">
            <input
              id="t-source"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              onBlur={() =>
                flushIfChanged(
                  "source",
                  source || null,
                  savedRef.current?.source ?? null,
                )
              }
              placeholder="e.g. RQ-7B/2-12-B/sensor-04"
              className="w-full px-3 py-2"
              style={inputStyle}
            />
          </Labeled>
          <Labeled label="Remarks" id="t-remarks">
            <textarea
              id="t-remarks"
              value={remarks}
              rows={4}
              onChange={(e) => setRemarks(e.target.value)}
              onBlur={() =>
                flushIfChanged(
                  "remarks",
                  remarks || null,
                  savedRef.current?.remarks ?? null,
                )
              }
              placeholder="Free-form notes — these land in the CoT <remarks> element when published."
              className="w-full px-3 py-2"
              style={{ ...inputStyle, resize: "vertical", minHeight: 88 }}
            />
          </Labeled>
        </Section>

        <Section
          title="Audit"
          hint={`${events.length} event${events.length === 1 ? "" : "s"} on this target.`}
        >
          {events.length === 0 ? (
            <p className="text-[12px]" style={{ color: "var(--tw-ink-dim)" }}>
              No audit events yet.
            </p>
          ) : (
            <ul className="space-y-2">
              {events.slice(0, 20).map((e) => (
                <li
                  key={e.id}
                  className="px-3 py-2"
                  style={{
                    background: "var(--tw-bg-panel)",
                    borderWidth: 1,
                    borderStyle: "solid",
                    borderColor: "var(--tw-border)",
                    borderRadius: "var(--tw-radius)",
                  }}
                >
                  <div className="flex items-baseline justify-between gap-3">
                    <code
                      className="text-[11px]"
                      style={{
                        color: "var(--tw-accent)",
                        fontFamily: "var(--tw-font-mono)",
                      }}
                    >
                      {e.event_type}
                    </code>
                    <code
                      className="text-[10px]"
                      style={{
                        color: "var(--tw-ink-dim)",
                        fontFamily: "var(--tw-font-mono)",
                      }}
                    >
                      {new Date(e.occurred_at).toLocaleString()}
                    </code>
                  </div>
                  {e.justification && (
                    <p
                      className="text-[12px] mt-1"
                      style={{ color: "var(--tw-ink-muted)" }}
                    >
                      {e.justification}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>
    </main>
  );
}

const inputStyle: React.CSSProperties = {
  background: "var(--tw-bg)",
  borderWidth: 1,
  borderStyle: "solid",
  borderColor: "var(--tw-border)",
  borderRadius: "var(--tw-radius)",
  color: "var(--tw-ink)",
  fontFamily: "var(--tw-font-body)",
  minHeight: 44,
};

function Section({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <section
      className="space-y-3"
      style={{
        background: "var(--tw-bg-panel)",
        borderWidth: 1,
        borderStyle: "solid",
        borderColor: "var(--tw-border)",
        borderRadius: "var(--tw-radius)",
        padding: 16,
      }}
    >
      <header className="space-y-0.5">
        <h2 className="tw-display text-base" style={{ color: "var(--tw-ink)" }}>
          {title}
        </h2>
        {hint && (
          <p className="text-[11px]" style={{ color: "var(--tw-ink-dim)" }}>
            {hint}
          </p>
        )}
      </header>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

function Labeled({
  label,
  id,
  children,
}: {
  label: string;
  id: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <label htmlFor={id} className="block space-y-1">
      <span
        className="tw-eyebrow text-[10px]"
        style={{ color: "var(--tw-ink-dim)" }}
      >
        {label}
      </span>
      {children}
    </label>
  );
}
