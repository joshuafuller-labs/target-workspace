import React from "react";
import { useState } from "react";

import { api } from "../api";
import type { Board, Target } from "../types";
import { CotTypePicker } from "./CotTypePicker";

interface Props {
  board: Board;
  onCreated: (t: Target) => void;
  onCancel: () => void;
}

export function NewTargetForm({ board, onCreated, onCancel }: Props): React.JSX.Element {
  const firstColumnId = board.columns[0]?.id ?? "";
  const [name, setName] = useState("BISON-01");
  const [cotType, setCotType] = useState("a-u-G");
  const [lat, setLat] = useState("33.4484");
  const [lon, setLon] = useState("-112.0740");
  const [confidence, setConfidence] = useState("0.87");
  const [columnId, setColumnId] = useState(firstColumnId);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const target = await api.createTarget({
        board_id: board.id,
        column_id: columnId,
        name,
        cot_type: cotType || undefined,
        lat: Number(lat),
        lon: Number(lon),
        confidence: confidence ? Number(confidence) : null,
        time: new Date().toISOString(),
      });
      onCreated(target);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed top-0 left-0 w-[100dvw] h-[100dvh] bg-black/70 z-50 overflow-y-auto flex items-end justify-center desktop:items-center desktop:p-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-2xl bg-neutral-900 border border-neutral-800 p-4 desktop:p-6 space-y-4 rounded-t-lg desktop:rounded-lg desktop:my-8"
      >
        <h2 className="text-lg font-semibold">New target</h2>

        <Field label="Callsign" id="t-name">
          <input
            id="t-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full px-3 py-2 bg-neutral-950 border border-neutral-800 rounded text-neutral-100 focus:border-amber-500 focus:outline-none"
            required
          />
        </Field>

        <div className="space-y-1">
          <label className="block text-xs uppercase tracking-wider text-neutral-400">
            CoT type
          </label>
          <CotTypePicker value={cotType} onChange={setCotType} />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Latitude" id="t-lat">
            <input
              id="t-lat"
              value={lat}
              onChange={(e) => setLat(e.target.value)}
              className="w-full px-3 py-2 bg-neutral-950 border border-neutral-800 rounded text-neutral-100 focus:border-amber-500 focus:outline-none font-mono"
              required
            />
          </Field>
          <Field label="Longitude" id="t-lon">
            <input
              id="t-lon"
              value={lon}
              onChange={(e) => setLon(e.target.value)}
              className="w-full px-3 py-2 bg-neutral-950 border border-neutral-800 rounded text-neutral-100 focus:border-amber-500 focus:outline-none font-mono"
              required
            />
          </Field>
        </div>

        <Field label="Confidence (0–1)" id="t-conf">
          <input
            id="t-conf"
            value={confidence}
            onChange={(e) => setConfidence(e.target.value)}
            className="w-full px-3 py-2 bg-neutral-950 border border-neutral-800 rounded text-neutral-100 focus:border-amber-500 focus:outline-none font-mono"
          />
        </Field>

        <Field label="Initial column" id="t-col">
          <select
            id="t-col"
            value={columnId}
            onChange={(e) => setColumnId(e.target.value)}
            className="w-full px-3 py-2 bg-neutral-950 border border-neutral-800 rounded text-neutral-100 focus:border-amber-500 focus:outline-none"
          >
            {board.columns.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </Field>

        {error && (
          <p className="text-sm text-red-400 bg-red-950/30 border border-red-900/40 rounded px-3 py-2">
            {error}
          </p>
        )}

        <div className="flex gap-2 justify-end pt-2">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 bg-neutral-800 hover:bg-neutral-700 rounded text-sm"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={busy}
            className="px-4 py-2 bg-amber-500 hover:bg-amber-400 disabled:bg-neutral-700 text-neutral-950 font-semibold rounded text-sm"
          >
            {busy ? "Creating…" : "Add target"}
          </button>
        </div>
      </form>
    </div>
  );
}

function Field({
  label,
  id,
  children,
}: {
  label: string;
  id: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-xs uppercase tracking-wider text-neutral-400">
        {label}
      </label>
      {children}
    </div>
  );
}
