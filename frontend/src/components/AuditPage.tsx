import React from "react";
import { useEffect, useState } from "react";

import { navigate } from "../router";
import type { AuditEventOut, UserOut } from "../types";

interface Props {
  user: UserOut;
}

interface Filters {
  event_type: string;
  q: string;
  from: string;
  to: string;
  actor_id: string;
}

const EMPTY: Filters = { event_type: "", q: "", from: "", to: "", actor_id: "" };

/** Full-screen audit log (tw-81p) — filterable list + CSV export.
 *
 *  Replaces the bottom-strip audit aside for AAR / compliance review.
 *  Filters compose; live-tail via WS is a follow-up.
 */
export function AuditPage({ user: _user }: Props): React.JSX.Element {
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [events, setEvents] = useState<AuditEventOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void (async () => {
      try {
        const qs = new URLSearchParams();
        if (filters.event_type) qs.set("event_type", filters.event_type);
        if (filters.q) qs.set("q", filters.q);
        if (filters.from) qs.set("from", filters.from);
        if (filters.to) qs.set("to", filters.to);
        if (filters.actor_id) qs.set("actor_id", filters.actor_id);
        qs.set("limit", "200");
        const res = await fetch(`/v1/audit?${qs.toString()}`, {
          credentials: "include",
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const rows = (await res.json()) as AuditEventOut[];
        if (!cancelled) setEvents(rows);
      } catch (e) {
        if (!cancelled) setError(String((e as Error).message ?? e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [filters]);

  function update<K extends keyof Filters>(k: K, v: Filters[K]): void {
    setFilters((prev) => ({ ...prev, [k]: v }));
  }

  function exportCsv(): void {
    const qs = new URLSearchParams();
    if (filters.event_type) qs.set("event_type", filters.event_type);
    if (filters.q) qs.set("q", filters.q);
    if (filters.from) qs.set("from", filters.from);
    if (filters.to) qs.set("to", filters.to);
    if (filters.actor_id) qs.set("actor_id", filters.actor_id);
    window.location.assign(`/v1/audit/export.csv?${qs.toString()}`);
  }

  return (
    <main className="min-h-screen bg-neutral-950 text-neutral-100 p-6">
      <header className="mb-4 flex items-center gap-4">
        <button
          type="button"
          className="text-neutral-400 hover:text-neutral-100"
          onClick={() => navigate("/")}
        >
          ← Board
        </button>
        <h1 className="text-xl font-semibold">Audit Log</h1>
        <button
          type="button"
          className="ml-auto rounded bg-neutral-800 px-3 py-1 text-sm hover:bg-neutral-700"
          onClick={exportCsv}
        >
          Export CSV
        </button>
      </header>

      <section className="mb-4 grid grid-cols-1 gap-2 md:grid-cols-5">
        <input
          aria-label="Filter by event type"
          placeholder="event_type (e.g. auth.login.success)"
          className="rounded bg-neutral-900 px-2 py-1 text-sm"
          value={filters.event_type}
          onChange={(e) => update("event_type", e.target.value)}
        />
        <input
          aria-label="Full-text search"
          placeholder="search (q)"
          className="rounded bg-neutral-900 px-2 py-1 text-sm"
          value={filters.q}
          onChange={(e) => update("q", e.target.value)}
        />
        <input
          aria-label="From"
          type="datetime-local"
          className="rounded bg-neutral-900 px-2 py-1 text-sm"
          value={filters.from}
          onChange={(e) => update("from", e.target.value)}
        />
        <input
          aria-label="To"
          type="datetime-local"
          className="rounded bg-neutral-900 px-2 py-1 text-sm"
          value={filters.to}
          onChange={(e) => update("to", e.target.value)}
        />
        <input
          aria-label="Actor id"
          placeholder="actor_id"
          className="rounded bg-neutral-900 px-2 py-1 text-sm"
          value={filters.actor_id}
          onChange={(e) => update("actor_id", e.target.value)}
        />
      </section>

      {error && (
        <div className="mb-4 rounded bg-red-950 px-3 py-2 text-sm text-red-200">
          {error}
        </div>
      )}

      <table className="w-full border-collapse text-sm">
        <thead className="border-b border-neutral-800 text-left text-neutral-400">
          <tr>
            <th className="py-2 pr-2">Time</th>
            <th className="py-2 pr-2">Event</th>
            <th className="py-2 pr-2">Actor</th>
            <th className="py-2 pr-2">Target</th>
            <th className="py-2 pr-2">Justification</th>
            <th className="py-2 pr-2">Metadata</th>
          </tr>
        </thead>
        <tbody>
          {events.map((ev) => (
            <tr key={ev.id} className="border-b border-neutral-900 align-top">
              <td className="py-2 pr-2 font-mono text-xs">{ev.occurred_at}</td>
              <td className="py-2 pr-2">{ev.event_type}</td>
              <td className="py-2 pr-2 font-mono text-xs">
                {ev.actor_id ? ev.actor_id.slice(0, 8) : "—"}
              </td>
              <td className="py-2 pr-2 font-mono text-xs">
                {ev.target_id ? ev.target_id.slice(0, 8) : "—"}
              </td>
              <td className="py-2 pr-2">{ev.justification || "—"}</td>
              <td className="py-2 pr-2 font-mono text-xs">
                {Object.keys(ev.metadata || {}).length === 0
                  ? "—"
                  : JSON.stringify(ev.metadata)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {loading && <div className="mt-4 text-neutral-500">Loading…</div>}
      {!loading && events.length === 0 && (
        <div className="mt-4 text-neutral-500">No events match these filters.</div>
      )}
    </main>
  );
}
