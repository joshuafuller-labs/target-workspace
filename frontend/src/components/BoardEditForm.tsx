import React from "react";
import { useState } from "react";

import { api, ApiError } from "../api";
import type { Board, ThemeName } from "../types";

interface Props {
  board: Board;
  onSaved: (board: Board) => void;
  onDeleted: (boardId: string) => void;
  onCancel: () => void;
}

const THEMES: ReadonlyArray<{ name: ThemeName; hint: string }> = [
  { name: "neutral", hint: "Editorial baseline" },
  { name: "tactical", hint: "ATAK / Toughbook" },
  { name: "federal", hint: "Govtech navy + gold" },
  { name: "sar", hint: "Outdoor / SAR" },
  { name: "ics", hint: "EOC / FEMA ICS" },
];

/** Modal/bottom-sheet for renaming a board, changing its theme,
 *  flipping its transition policy, or deleting it. Column add / edit
 *  / delete lives in a separate flow (tw-itn). */
export function BoardEditForm({
  board,
  onSaved,
  onDeleted,
  onCancel,
}: Props): React.JSX.Element {
  const [name, setName] = useState(board.name);
  const [theme, setTheme] = useState<ThemeName>(board.theme);
  const [transitions, setTransitions] = useState<
    "unrestricted" | "sequential"
  >(board.transitions);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  async function handleSave(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const payload: {
      name?: string;
      theme?: ThemeName;
      transitions?: "unrestricted" | "sequential";
    } = {};
    if (name.trim() !== board.name) payload.name = name.trim();
    if (theme !== board.theme) payload.theme = theme;
    if (transitions !== board.transitions) payload.transitions = transitions;
    if (Object.keys(payload).length === 0) {
      onCancel();
      return;
    }
    try {
      const updated = await api.updateBoard(board.id, payload);
      onSaved(updated);
    } catch (err) {
      setError(extractDetail(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await api.deleteBoard(board.id);
      onDeleted(board.id);
    } catch (err) {
      setError(extractDetail(err));
      setConfirmDelete(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-label={`Edit board ${board.name}`}
      onClick={onCancel}
      className="fixed top-0 left-0 w-[100dvw] h-[100dvh] z-50 flex items-end justify-center desktop:items-center desktop:p-4"
      style={{ background: "rgba(0,0,0,0.7)" }}
    >
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSave}
        className="w-full max-w-lg max-h-[92vh] overflow-y-auto p-4 desktop:p-6 space-y-4 rounded-t-[var(--tw-radius)] desktop:rounded-[var(--tw-radius)]"
        style={{
          background: "var(--tw-bg)",
          borderWidth: 1,
          borderStyle: "solid",
          borderColor: "var(--tw-border)",
        }}
      >
        <header className="flex items-start justify-between gap-3">
          <div>
            <p
              className="tw-eyebrow text-[10px]"
              style={{ color: "var(--tw-brand)" }}
            >
              Edit board
            </p>
            <h2 className="tw-display text-lg desktop:text-xl mt-0.5">
              {board.name}
            </h2>
          </div>
          <button
            type="button"
            onClick={onCancel}
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
        </header>

        <Labeled label="Name" id="board-name">
          <input
            id="board-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            minLength={1}
            maxLength={120}
            className="w-full px-3 py-2"
            style={inputStyle}
          />
        </Labeled>

        <fieldset>
          <legend className="tw-eyebrow text-[10px]" style={legendStyle}>
            Theme
          </legend>
          <div className="grid grid-cols-1 desktop:grid-cols-2 gap-2 mt-2">
            {THEMES.map((t) => {
              const active = t.name === theme;
              return (
                <button
                  key={t.name}
                  type="button"
                  onClick={() => setTheme(t.name)}
                  aria-pressed={active}
                  className="text-left px-3 py-2"
                  style={{
                    background: active
                      ? "var(--tw-accent-bg)"
                      : "var(--tw-bg-panel)",
                    color: active ? "var(--tw-accent-ink)" : "var(--tw-ink)",
                    borderWidth: 1,
                    borderStyle: "solid",
                    borderColor: active
                      ? "var(--tw-accent)"
                      : "var(--tw-border)",
                    borderRadius: "var(--tw-radius)",
                    minHeight: 52,
                  }}
                >
                  <div className="text-sm font-medium">{t.name}</div>
                  <div
                    className="text-[11px]"
                    style={{
                      color: active
                        ? "var(--tw-accent-ink)"
                        : "var(--tw-ink-dim)",
                    }}
                  >
                    {t.hint}
                  </div>
                </button>
              );
            })}
          </div>
        </fieldset>

        <fieldset>
          <legend className="tw-eyebrow text-[10px]" style={legendStyle}>
            Transition policy
          </legend>
          <div className="grid grid-cols-2 gap-2 mt-2">
            {(["unrestricted", "sequential"] as const).map((opt) => {
              const active = opt === transitions;
              return (
                <button
                  key={opt}
                  type="button"
                  onClick={() => setTransitions(opt)}
                  aria-pressed={active}
                  className="text-left px-3 py-2 tw-eyebrow text-[11px]"
                  style={{
                    background: active
                      ? "var(--tw-accent-bg)"
                      : "var(--tw-bg-panel)",
                    color: active ? "var(--tw-accent-ink)" : "var(--tw-ink)",
                    borderWidth: 1,
                    borderStyle: "solid",
                    borderColor: active
                      ? "var(--tw-accent)"
                      : "var(--tw-border)",
                    borderRadius: "var(--tw-radius)",
                    minHeight: 44,
                  }}
                >
                  {opt}
                </button>
              );
            })}
          </div>
        </fieldset>

        {error && (
          <p
            className="text-sm px-3 py-2"
            style={{
              background: "var(--tw-bg-panel)",
              borderLeftWidth: 3,
              borderLeftStyle: "solid",
              borderLeftColor: "var(--tw-approval)",
              color: "var(--tw-approval)",
            }}
          >
            {error}
          </p>
        )}

        <footer className="flex flex-col-reverse desktop:flex-row items-stretch desktop:items-center desktop:justify-between gap-3 pt-2">
          {!confirmDelete ? (
            <button
              type="button"
              onClick={() => setConfirmDelete(true)}
              className="tw-eyebrow text-[11px] px-3"
              style={{
                color: "var(--tw-approval)",
                background: "transparent",
                borderWidth: 1,
                borderStyle: "solid",
                borderColor: "var(--tw-approval)",
                borderRadius: "var(--tw-radius)",
                minHeight: 44,
              }}
            >
              Delete board
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <span
                className="tw-eyebrow text-[10px]"
                style={{ color: "var(--tw-approval)" }}
              >
                Sure?
              </span>
              <button
                type="button"
                onClick={handleDelete}
                disabled={busy}
                className="tw-eyebrow text-[11px] px-3"
                style={{
                  background: "var(--tw-approval)",
                  color: "var(--tw-bg)",
                  borderRadius: "var(--tw-radius)",
                  minHeight: 44,
                }}
              >
                Yes, delete
              </button>
              <button
                type="button"
                onClick={() => setConfirmDelete(false)}
                className="tw-eyebrow text-[11px] px-3"
                style={{
                  color: "var(--tw-ink-muted)",
                  borderWidth: 1,
                  borderStyle: "solid",
                  borderColor: "var(--tw-border)",
                  borderRadius: "var(--tw-radius)",
                  minHeight: 44,
                }}
              >
                Cancel
              </button>
            </div>
          )}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onCancel}
              className="tw-eyebrow text-[11px] px-3"
              style={{
                color: "var(--tw-ink-muted)",
                background: "transparent",
                minHeight: 44,
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={busy}
              className="tw-eyebrow text-[11px] px-4"
              style={{
                background: "var(--tw-accent-bg)",
                color: "var(--tw-accent-ink)",
                borderRadius: "var(--tw-radius)",
                minHeight: 44,
              }}
            >
              {busy ? "Saving…" : "Save"}
            </button>
          </div>
        </footer>
      </form>
    </div>
  );
}

function extractDetail(err: unknown): string {
  if (err instanceof ApiError) {
    if (typeof err.detail === "object" && err.detail && "detail" in err.detail) {
      return String((err.detail as { detail: unknown }).detail);
    }
    return err.message;
  }
  return String(err);
}

const inputStyle: React.CSSProperties = {
  background: "var(--tw-bg-panel)",
  borderWidth: 1,
  borderStyle: "solid",
  borderColor: "var(--tw-border)",
  borderRadius: "var(--tw-radius)",
  color: "var(--tw-ink)",
  fontFamily: "var(--tw-font-body)",
  minHeight: 44,
};

const legendStyle: React.CSSProperties = {
  color: "var(--tw-ink-dim)",
};

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
