import React from "react";
import { useState } from "react";

import type { Board, Target } from "../types";

interface Props {
  target: Target;
  toColumn: Board["columns"][number];
  board: Board;
  onConfirm: (approvingRole: string, justification: string | null) => void;
  onCancel: () => void;
}

/**
 * Small dialog asking for the approving role + optional justification when
 * a card is dropped into an approval-gated column. Reuses the modal pattern
 * from TargetDetail so the look stays cohesive across the kanban.
 */
export function ApprovalPrompt({
  target,
  toColumn,
  board,
  onConfirm,
  onCancel,
}: Props): React.JSX.Element {
  const [role, setRole] = useState("");
  const [justification, setJustification] = useState("");
  const [busy, setBusy] = useState(false);

  function submit(e: React.FormEvent): void {
    e.preventDefault();
    if (!role.trim()) return;
    setBusy(true);
    onConfirm(role.trim(), justification.trim() || null);
  }

  return (
    <div
      role="dialog"
      aria-label="Approval required"
      onClick={onCancel}
      className="fixed top-0 left-0 w-[100dvw] h-[100dvh] z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.6)" }}
    >
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
        className="w-full max-w-md p-5 space-y-4"
        style={{
          background: "var(--tw-bg)",
          borderWidth: 1,
          borderStyle: "solid",
          borderColor: "var(--tw-approval)",
          borderRadius: "var(--tw-radius)",
        }}
      >
        <div>
          <p
            className="tw-eyebrow text-[10px]"
            style={{ color: "var(--tw-approval)" }}
          >
            Approval required
          </p>
          <h2
            className="tw-display text-lg mt-1"
            style={{ color: "var(--tw-ink)" }}
          >
            Move {target.name} → {toColumn.name}
          </h2>
          <p
            className="text-xs mt-1"
            style={{ color: "var(--tw-ink-muted)", fontFamily: "var(--tw-font-body)" }}
          >
            Entering this column on{" "}
            <span style={{ color: "var(--tw-ink)" }}>{board.name}</span> is
            gated. Provide an approving role and a brief justification — this
            lands in the audit log.
          </p>
          {(target.geometry_quality === "bearing-only" ||
            target.geometry_quality === "single-source") && (
            <p
              className="text-xs mt-3 p-2"
              style={{
                color: "var(--tw-approval)",
                borderWidth: 1,
                borderStyle: "solid",
                borderColor: "var(--tw-approval)",
                borderRadius: "var(--tw-radius)",
                fontFamily: "var(--tw-font-body)",
              }}
            >
              ⚠ Geometry quality is <strong>{target.geometry_quality}</strong>.
              Standard RoE practice requires <strong>corroborated</strong> or
              better before kinetic engagement. The audit log will record
              your override.
            </p>
          )}
        </div>

        <label className="block">
          <span
            className="tw-eyebrow block text-[10px] mb-1"
            style={{ color: "var(--tw-ink-muted)" }}
          >
            Approving role
          </span>
          <input
            value={role}
            onChange={(e) => setRole(e.target.value)}
            placeholder="e.g. OPS-O, CDR, ASAC, OSC"
            autoFocus
            className="w-full px-3 py-2 text-sm"
            style={{
              background: "var(--tw-bg-panel)",
              borderWidth: 1,
              borderStyle: "solid",
              borderColor: "var(--tw-border)",
              borderRadius: "var(--tw-radius)",
              color: "var(--tw-ink)",
              fontFamily: "var(--tw-font-mono)",
              minHeight: 44,
            }}
          />
        </label>

        <label className="block">
          <span
            className="tw-eyebrow block text-[10px] mb-1"
            style={{ color: "var(--tw-ink-muted)" }}
          >
            Justification (optional)
          </span>
          <textarea
            value={justification}
            onChange={(e) => setJustification(e.target.value)}
            rows={3}
            placeholder="why is this approved now?"
            className="w-full px-3 py-2 text-sm resize-y"
            style={{
              background: "var(--tw-bg-panel)",
              borderWidth: 1,
              borderStyle: "solid",
              borderColor: "var(--tw-border)",
              borderRadius: "var(--tw-radius)",
              color: "var(--tw-ink)",
              fontFamily: "var(--tw-font-body)",
            }}
          />
        </label>

        <div className="flex justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onCancel}
            className="px-3 py-2 text-xs"
            style={{
              color: "var(--tw-ink-muted)",
              fontFamily: "var(--tw-font-body)",
              minHeight: 44,
            }}
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={busy || !role.trim()}
            className="tw-eyebrow px-4 py-2 text-[11px]"
            style={{
              background: "var(--tw-accent-bg)",
              color: "var(--tw-accent-ink)",
              borderRadius: "var(--tw-radius)",
              opacity: !role.trim() ? 0.5 : 1,
              minHeight: 44,
            }}
          >
            {busy ? "Approving…" : "Approve & move"}
          </button>
        </div>
      </form>
    </div>
  );
}
