// Tiny SPA router — history API + a useLocation() hook. Three routes:
//
//   /                       → kanban (default)
//   /targets/:id/edit       → TargetEditPage
//   /settings               → SettingsPage
//   /account                → AccountSecurityPage
//
// Hand-rolled because react-router would add ~30 KB to the bundle for
// three routes and a single navigate call. FastAPI's _spa_fallback in
// app.py already serves index.html for unknown paths, so the History API
// works with hard refreshes.

import { useEffect, useState } from "react";

type Listener = () => void;
const listeners = new Set<Listener>();

function notify(): void {
  for (const l of listeners) l();
}

export function navigate(path: string, replace = false): void {
  if (replace) {
    window.history.replaceState(null, "", path);
  } else {
    window.history.pushState(null, "", path);
  }
  notify();
}

export function useLocation(): string {
  const [path, setPath] = useState(() => window.location.pathname);
  useEffect(() => {
    function update(): void {
      setPath(window.location.pathname);
    }
    listeners.add(update);
    window.addEventListener("popstate", update);
    return () => {
      listeners.delete(update);
      window.removeEventListener("popstate", update);
    };
  }, []);
  return path;
}

/** Match the location against a small set of patterns. Returns the first
 *  matching key and its captured params (or `null` if nothing matches).
 *  Patterns use `:name` placeholders. */
export function matchRoute<K extends string>(
  pathname: string,
  patterns: Record<K, string>,
): { key: K; params: Record<string, string> } | null {
  for (const [key, pattern] of Object.entries(patterns) as [K, string][]) {
    const segs = pattern.split("/").filter(Boolean);
    const parts = pathname.split("/").filter(Boolean);
    if (segs.length !== parts.length) continue;
    const params: Record<string, string> = {};
    let ok = true;
    for (let i = 0; i < segs.length; i += 1) {
      const s = segs[i];
      const p = parts[i];
      if (s.startsWith(":")) {
        params[s.slice(1)] = p;
      } else if (s !== p) {
        ok = false;
        break;
      }
    }
    if (ok) return { key, params };
  }
  return null;
}
