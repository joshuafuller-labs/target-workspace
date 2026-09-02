import React from "react";
import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import { navigate } from "../router";
import type {
  AuditEventOut,
  Board,
  ObservationOut,
  Target,
  TargetUpdatePayload,
} from "../types";
import { LivePositionsPanel } from "./LivePositionsPanel";

interface Props {
  target: Target;
  board: Board;
  onClose: () => void;
  onMoved: (t: Target) => void;
}

/** Common CoT type suggestions surfaced as datalist hints. Not exhaustive
 *  — the field accepts any MIL-STD-2525-style string — these are the ones
 *  that show up across the bundled scenarios. */
const COT_TYPE_HINTS = [
  "a-h-G",
  "a-h-G-E-V",
  "a-h-G-E-V-C",
  "a-h-G-U-C",
  "a-h-G-I",
  "a-h-A",
  "a-s-A",
  "a-u-A",
  "a-u-G",
  "a-u-G-I",
  "a-u-G-E-V",
  "a-u-G-U-C",
  "a-f-G-U-C",
];

export function TargetDetail({
  target: initialTarget,
  board,
  onClose,
  onMoved,
}: Props): React.JSX.Element {
  // Local copy so PATCH responses (version bumps) reflect immediately.
  const [target, setTarget] = useState<Target>(initialTarget);
  const [currentColumnId, setCurrentColumnId] = useState<string>("");
  const [destColumnId, setDestColumnId] = useState<string>("");
  const [approvingRole, setApprovingRole] = useState<string>("supervisor");
  const [justification, setJustification] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [events, setEvents] = useState<AuditEventOut[]>([]);
  const [observations, setObservations] = useState<ObservationOut[]>([]);

  // Edit state — initialized from target, mutated locally, PATCHed on blur
  // or via explicit Save. Tracking the last-saved value lets us know when
  // a field is "dirty" without an extra `dirty` flag per input.
  const [cotType, setCotType] = useState(target.cot_type);
  const [remarks, setRemarks] = useState(target.remarks ?? "");
  const [source, setSource] = useState(target.source ?? "");
  const lastSavedRef = useRef({
    cot_type: target.cot_type,
    remarks: target.remarks ?? "",
    source: target.source ?? "",
  });

  useEffect(() => {
    void (async () => {
      try {
        const audit = await api.listAudit(target.id);
        setEvents(audit);
        const lastTrans = audit.find((e) => e.event_type === "transitioned");
        const col = lastTrans?.to_column_id ?? audit[audit.length - 1]?.to_column_id ?? null;
        if (col) setCurrentColumnId(col);
      } catch (err) {
        setError(String(err));
      }
    })();
    void (async () => {
      try {
        setObservations(await api.listObservations(target.id));
      } catch {
        // Observations are advisory; failure shouldn't block the modal.
      }
    })();
  }, [target.id]);

  async function saveField(payload: TargetUpdatePayload): Promise<void> {
    setError(null);
    try {
      const updated = await api.updateTarget(target.id, payload);
      setTarget(updated);
      lastSavedRef.current = {
        cot_type: updated.cot_type,
        remarks: updated.remarks ?? "",
        source: updated.source ?? "",
      };
      // Refresh audit so the (future) edit event lands; harmless if not.
      setEvents(await api.listAudit(target.id));
    } catch (err) {
      setError(String(err));
    }
  }

  function flushCotType(): void {
    if (!cotType.trim()) {
      setCotType(lastSavedRef.current.cot_type);
      return;
    }
    if (cotType !== lastSavedRef.current.cot_type) {
      void saveField({ cot_type: cotType });
    }
  }

  function flushRemarks(): void {
    if (remarks !== lastSavedRef.current.remarks) {
      void saveField({ remarks: remarks || null });
    }
  }

  function flushSource(): void {
    if (source !== lastSavedRef.current.source) {
      void saveField({ source: source || null });
    }
  }

  const destColumn = board.columns.find((c) => c.id === destColumnId);
  const requiresApproval = destColumn?.requires_approval ?? false;

  async function handleMove(): Promise<void> {
    if (!destColumnId) return;
    setBusy(true);
    setError(null);
    try {
      const moved = await api.moveTarget(target.id, destColumnId, {
        justification: justification || undefined,
        approving_role: requiresApproval ? approvingRole : undefined,
      });
      setTarget(moved);
      onMoved(moved);
      setEvents(await api.listAudit(target.id));
      setCurrentColumnId(destColumnId);
      setDestColumnId("");
      setJustification("");
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  const inputBase: React.CSSProperties = {
    background: "var(--tw-bg-panel)",
    borderWidth: 1,
    borderStyle: "solid",
    borderColor: "var(--tw-border)",
    borderRadius: "var(--tw-radius)",
    color: "var(--tw-ink)",
    fontFamily: "var(--tw-font-mono)",
    minHeight: 44,
    width: "100%",
    padding: "8px 12px",
    fontSize: 13,
  };

  return (
    <div
      role="dialog"
      aria-label={`Target ${target.name}`}
      onClick={onClose}
      // Desktop: centered modal with padding. Mobile: bottom-aligned
      // bottom-sheet so the inner content can be a comfortable full-
      // viewport width without bleeding off either edge.
      className="fixed top-0 left-0 w-[100dvw] h-[100dvh] z-50 flex items-end justify-center desktop:items-center desktop:p-4"
      style={{ background: "rgba(0,0,0,0.7)" }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-2xl max-h-[92vh] overflow-y-auto p-4 desktop:p-6 space-y-5 rounded-t-[var(--tw-radius)] desktop:rounded-[var(--tw-radius)]"
        style={{
          background: "var(--tw-bg)",
          borderWidth: 1,
          borderStyle: "solid",
          borderColor: "var(--tw-border)",
        }}
      >
        <header className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p
              className="tw-eyebrow text-[10px]"
              style={{ color: "var(--tw-brand)" }}
            >
              Target · v{target.version}
            </p>
            <h2
              className="tw-display text-xl mt-0.5 truncate"
              style={{ color: "var(--tw-ink)" }}
            >
              {target.name}
            </h2>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => navigate(`/targets/${target.id}/edit`)}
              className="tw-eyebrow text-[10px] px-3"
              style={{
                background: "transparent",
                borderWidth: 1,
                borderStyle: "solid",
                borderColor: "var(--tw-border)",
                borderRadius: "var(--tw-radius)",
                color: "var(--tw-ink-muted)",
                minHeight: 36,
              }}
              title="Open in deep-linkable editor"
            >
              Open editor ↗
            </button>
            <button
              onClick={onClose}
              aria-label="Close"
              className="p-2 -m-2"
              style={{
                color: "var(--tw-ink-muted)",
                minWidth: 44,
                minHeight: 44,
              }}
            >
              ✕
            </button>
          </div>
        </header>

        {/* Editable CoT type + source */}
        <section className="space-y-3">
          <label className="block">
            <span
              className="tw-eyebrow block text-[10px] mb-1"
              style={{ color: "var(--tw-ink-muted)" }}
            >
              CoT type
            </span>
            <input
              value={cotType}
              onChange={(e) => setCotType(e.target.value)}
              onBlur={flushCotType}
              onKeyDown={(e) => {
                if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                if (e.key === "Escape") {
                  setCotType(lastSavedRef.current.cot_type);
                  (e.target as HTMLInputElement).blur();
                }
              }}
              list="tw-cot-hints"
              placeholder="a-h-G, a-h-A, a-s-A, …"
              style={inputBase}
            />
            <datalist id="tw-cot-hints">
              {COT_TYPE_HINTS.map((h) => (
                <option key={h} value={h} />
              ))}
            </datalist>
          </label>

          <label className="block">
            <span
              className="tw-eyebrow block text-[10px] mb-1"
              style={{ color: "var(--tw-ink-muted)" }}
            >
              Source / attribution
            </span>
            <input
              value={source}
              onChange={(e) => setSource(e.target.value)}
              onBlur={flushSource}
              onKeyDown={(e) => {
                if (e.key === "Enter") (e.target as HTMLInputElement).blur();
              }}
              placeholder="e.g. CV-ATR (MQ-9), HUMINT (HCT-7), Ku-band radar"
              style={inputBase}
            />
          </label>
        </section>

        {/* Read-only metadata */}
        <dl
          className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm"
          style={{
            fontFamily: "var(--tw-font-mono)",
            color: "var(--tw-ink)",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          <dt className="tw-eyebrow text-[10px]" style={{ color: "var(--tw-ink-muted)" }}>
            Position
          </dt>
          <dd>
            {target.lat.toFixed(4)}, {target.lon.toFixed(4)}
          </dd>
          {target.confidence !== null && (
            <>
              <dt className="tw-eyebrow text-[10px]" style={{ color: "var(--tw-ink-muted)" }}>
                Confidence
              </dt>
              <dd>{target.confidence.toFixed(2)}</dd>
            </>
          )}
          <dt className="tw-eyebrow text-[10px]" style={{ color: "var(--tw-ink-muted)" }}>
            Time
          </dt>
          <dd className="truncate">{new Date(target.time).toLocaleString()}</dd>
          {target.ce !== null && (
            <>
              <dt className="tw-eyebrow text-[10px]" style={{ color: "var(--tw-ink-muted)" }}>
                CE
              </dt>
              <dd>{target.ce} m</dd>
            </>
          )}
        </dl>

        {/* Remarks — editable, free-form, surfaces in CoT publish */}
        <label className="block">
          <span
            className="tw-eyebrow block text-[10px] mb-1"
            style={{ color: "var(--tw-ink-muted)" }}
          >
            Remarks (broadcast in CoT)
          </span>
          <textarea
            value={remarks}
            onChange={(e) => setRemarks(e.target.value)}
            onBlur={flushRemarks}
            rows={3}
            placeholder="Operator note — surfaces on every published CoT and in ATAK"
            style={{
              ...inputBase,
              fontFamily: "var(--tw-font-body)",
              minHeight: 80,
              resize: "vertical",
            }}
          />
          <p
            className="text-[10px] mt-1"
            style={{ color: "var(--tw-ink-dim)", fontFamily: "var(--tw-font-body)" }}
          >
            A deep-link back to this card is appended automatically on publish.
          </p>
        </label>

        {Object.keys(target.custom_fields).length > 0 && (
          <div className="border-t pt-3" style={{ borderColor: "var(--tw-border)" }}>
            <p
              className="tw-eyebrow text-[10px] mb-1.5"
              style={{ color: "var(--tw-ink-muted)" }}
            >
              Custom fields
            </p>
            <pre
              className="text-xs overflow-x-auto p-2"
              style={{
                background: "var(--tw-bg-panel)",
                borderWidth: 1,
                borderStyle: "solid",
                borderColor: "var(--tw-border)",
                borderRadius: "var(--tw-radius)",
                fontFamily: "var(--tw-font-mono)",
              }}
            >
              {JSON.stringify(target.custom_fields, null, 2)}
            </pre>
          </div>
        )}

        <section
          className="border-t pt-4 space-y-3"
          style={{ borderColor: "var(--tw-border)" }}
        >
          <p
            className="tw-eyebrow text-[10px]"
            style={{ color: "var(--tw-ink-muted)" }}
          >
            Move
          </p>
          <select
            value={destColumnId}
            onChange={(e) => setDestColumnId(e.target.value)}
            style={{ ...inputBase, fontFamily: "var(--tw-font-body)" }}
          >
            <option value="">Pick a destination column…</option>
            {board.columns
              .filter((c) => c.id !== currentColumnId)
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} {c.requires_approval ? "(approval required)" : ""}
                </option>
              ))}
          </select>

          <input
            value={justification}
            onChange={(e) => setJustification(e.target.value)}
            placeholder="Justification (optional)"
            style={{ ...inputBase, fontFamily: "var(--tw-font-body)" }}
          />

          {requiresApproval && (
            <input
              value={approvingRole}
              onChange={(e) => setApprovingRole(e.target.value)}
              placeholder="Approving role (required)"
              style={{
                ...inputBase,
                fontFamily: "var(--tw-font-body)",
                borderColor: "var(--tw-approval)",
              }}
            />
          )}

          {error && (
            <p
              className="text-sm px-3 py-2"
              style={{
                color: "var(--tw-approval)",
                borderWidth: 1,
                borderStyle: "solid",
                borderColor: "var(--tw-approval)",
                borderRadius: "var(--tw-radius)",
                fontFamily: "var(--tw-font-body)",
              }}
            >
              {error}
            </p>
          )}

          <button
            onClick={handleMove}
            disabled={!destColumnId || busy}
            className="tw-eyebrow w-full text-[11px]"
            style={{
              background: "var(--tw-accent-bg)",
              color: "var(--tw-accent-ink)",
              borderRadius: "var(--tw-radius)",
              padding: "10px 16px",
              minHeight: 44,
              opacity: !destColumnId || busy ? 0.5 : 1,
            }}
          >
            {busy ? "Moving…" : "Move target"}
          </button>
        </section>

        <section className="border-t pt-4" style={{ borderColor: "var(--tw-border)" }}>
          <p
            className="tw-eyebrow text-[10px] mb-2"
            style={{ color: "var(--tw-ink-muted)" }}
          >
            Audit log ({events.length})
          </p>
          <ul className="space-y-1.5 max-h-48 overflow-y-auto">
            {events.map((e) => (
              <li
                key={e.id}
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
                  <span
                    className="tw-eyebrow text-[10px]"
                    style={{ color: "var(--tw-accent)" }}
                  >
                    {e.event_type}
                  </span>
                  <span style={{ color: "var(--tw-ink-dim)" }}>
                    {new Date(e.occurred_at).toLocaleTimeString()}
                  </span>
                </div>
                {e.justification && (
                  <div style={{ color: "var(--tw-ink-muted)" }} className="mt-1">
                    {e.justification}
                  </div>
                )}
              </li>
            ))}
            {events.length === 0 && (
              <li
                className="text-xs italic"
                style={{ color: "var(--tw-ink-dim)" }}
              >
                No events yet.
              </li>
            )}
          </ul>
        </section>

        <LivePositionsPanel
          callsigns={target.assigned_callsigns ?? []}
          targetLat={target.lat}
          targetLon={target.lon}
        />

        <section className="border-t pt-4" style={{ borderColor: "var(--tw-border)" }}>
          <p
            className="tw-eyebrow text-[10px] mb-2"
            style={{ color: "var(--tw-ink-muted)" }}
          >
            Observations ({observations.length})
          </p>
          <ul className="space-y-1.5 max-h-48 overflow-y-auto">
            {observations.map((o) => (
              <li
                key={o.id}
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
                  <span style={{ color: "var(--tw-ink-muted)" }}>
                    {new Date(o.observed_at).toLocaleString()}
                  </span>
                  {o.confidence !== null && (
                    <span style={{ color: "var(--tw-accent)" }}>
                      conf {(o.confidence * 100).toFixed(0)}%
                    </span>
                  )}
                </div>
                <div style={{ color: "var(--tw-ink-dim)" }} className="mt-1">
                  {o.lat.toFixed(4)}, {o.lon.toFixed(4)}
                  {o.source && <> · {o.source}</>}
                  {o.classification && <> · {o.classification}</>}
                </div>
              </li>
            ))}
            {observations.length === 0 && (
              <li className="text-xs italic" style={{ color: "var(--tw-ink-dim)" }}>
                No observations yet.
              </li>
            )}
          </ul>
        </section>
      </div>
    </div>
  );
}
