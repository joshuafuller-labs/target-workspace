import React from "react";
import { useState } from "react";

import { api } from "../api";
import { BRAND_NAME } from "../brand";
import type { Board } from "../types";

interface Props {
  onCreated: (board: Board) => void;
  /** When provided, render as a dismissible modal instead of the
   *  full-screen empty-state. Backdrop click + Cancel both fire it. */
  onCancel?: () => void;
}

const DEFAULT_TEMPLATE = [
  { name: "FIND", order: 0, requires_approval: false },
  { name: "FIX", order: 1, requires_approval: false },
  { name: "FINISH", order: 2, requires_approval: true },
  { name: "EXPLOIT", order: 3, requires_approval: false },
  { name: "ANALYZE", order: 4, requires_approval: false },
  { name: "DISSEM", order: 5, requires_approval: false },
];

export function NewBoardForm({ onCreated, onCancel }: Props): React.JSX.Element {
  const [name, setName] = useState("JSOTF F3EAD");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const board = await api.createBoard({ name, columns: DEFAULT_TEMPLATE });
      onCreated(board);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  const Wrapper = onCancel ? "div" : "main";
  return (
    <Wrapper
      className={
        onCancel
          ? "fixed top-0 left-0 w-[100dvw] h-[100dvh] z-50 flex items-end justify-center desktop:items-center desktop:p-4 bg-black/70"
          : "min-h-screen flex items-center justify-center p-8"
      }
      onClick={onCancel ? onCancel : undefined}
    >
      <form
        onSubmit={handleSubmit}
        onClick={(e) => e.stopPropagation()}
        className={
          onCancel
            ? "w-full max-w-md bg-neutral-900 border border-neutral-800 p-6 desktop:p-8 space-y-5 rounded-t-lg desktop:rounded-lg max-h-[92vh] overflow-y-auto"
            : "w-full max-w-md bg-neutral-900 border border-neutral-800 rounded-lg p-8 space-y-5"
        }
      >
        <div>
          <p className="text-[11px] uppercase tracking-[0.32em] text-neutral-500">
            {BRAND_NAME}
          </p>
          <h1 className="text-xl font-semibold mt-1">Create a board</h1>
          <p className="text-sm text-neutral-400 mt-2">
            Boards are workspace data — columns, transitions, approval gates. The F3EAD
            template ships ready to use; rename or customize the columns later.
          </p>
        </div>

        <div className="space-y-2">
          <label htmlFor="bname" className="block text-xs uppercase tracking-wider text-neutral-400">
            Board name
          </label>
          <input
            id="bname"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full px-3 py-2 bg-neutral-950 border border-neutral-800 rounded text-neutral-100 focus:border-amber-500 focus:outline-none"
            required
          />
        </div>

        <div className="text-xs text-neutral-500 space-y-1">
          <p>Default columns (F3EAD):</p>
          <ol className="list-decimal list-inside text-neutral-300 mt-1">
            {DEFAULT_TEMPLATE.map((c) => (
              <li key={c.name}>
                {c.name}
                {c.requires_approval ? " (approval required)" : ""}
              </li>
            ))}
          </ol>
        </div>

        {error && (
          <p className="text-sm text-red-400 bg-red-950/30 border border-red-900/40 rounded px-3 py-2">
            {error}
          </p>
        )}

        <div className="flex gap-2">
          {onCancel && (
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2 text-sm text-neutral-400 hover:text-neutral-200"
            >
              Cancel
            </button>
          )}
          <button
            type="submit"
            disabled={busy}
            className="flex-1 py-2 bg-amber-500 hover:bg-amber-400 disabled:bg-neutral-700 text-neutral-950 font-semibold rounded transition"
          >
            {busy ? "Creating…" : "Create board"}
          </button>
        </div>
      </form>
    </Wrapper>
  );
}
