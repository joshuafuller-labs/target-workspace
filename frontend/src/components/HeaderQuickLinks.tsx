import React from "react";
import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import { navigate } from "../router";

// Shipping the GH repo URL via env keeps fork builds correct. Defaults to
// the canonical repo so a misconfigured prod build still has working
// "view source" links.
const REPO_URL =
  (import.meta.env.VITE_REPO_URL as string | undefined) ??
  "https://github.com/joshuafuller-labs/target-workspace";

interface QuickLink {
  label: string;
  href: string;
  hint: string;
  external?: boolean;
  /** If set, intercepts the click and uses SPA navigation instead of a
   *  full page load. Used for in-app routes (Settings). */
  internal?: boolean;
}

const LINKS: QuickLink[] = [
  {
    label: "Settings",
    href: "/settings",
    hint: "Workspace settings",
    internal: true,
  },
  {
    label: "Audit Log",
    href: "/audit",
    hint: "Filterable audit history",
    internal: true,
  },
  {
    label: "Swagger UI",
    href: "/v1/docs",
    hint: "Interactive API explorer",
    external: true,
  },
  {
    label: "ReDoc",
    href: "/v1/redoc",
    hint: "Read-only API reference",
    external: true,
  },
  {
    label: "OpenAPI spec",
    href: "/v1/openapi.json",
    hint: "Raw OpenAPI 3.1 JSON",
    external: true,
  },
  {
    label: "Source",
    href: REPO_URL,
    hint: "GitHub repository",
    external: true,
  },
];

export function HeaderQuickLinks(): React.JSX.Element {
  const [open, setOpen] = useState(false);
  const [version, setVersion] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);

  // Fetch version lazily on first open — keeps the initial login render
  // free of an extra request, and the value is stable across the session.
  useEffect(() => {
    if (!open || version !== null) return;
    let cancelled = false;
    api
      .healthz()
      .then((r) => {
        if (!cancelled) setVersion(r.version);
      })
      .catch(() => {
        if (!cancelled) setVersion("unknown");
      });
    return () => {
      cancelled = true;
    };
  }, [open, version]);

  // Click-outside + Escape to dismiss.
  useEffect(() => {
    if (!open) return;
    function onPointer(e: PointerEvent): void {
      if (!rootRef.current) return;
      if (e.target instanceof Node && rootRef.current.contains(e.target)) return;
      setOpen(false);
    }
    function onKey(e: KeyboardEvent): void {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("pointerdown", onPointer);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onPointer);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Developer links"
        title="Developer links"
        className="tw-eyebrow text-[11px] px-3 py-1.5"
        style={{
          background: open ? "var(--tw-bg-panel)" : "transparent",
          borderWidth: 1,
          borderStyle: "solid",
          borderColor: "var(--tw-border)",
          borderRadius: "var(--tw-radius)",
          color: "var(--tw-ink-muted)",
          minHeight: 44,
        }}
      >
        {"{ }"} API
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 mt-1 z-30 min-w-[220px]"
          style={{
            background: "var(--tw-bg-panel)",
            borderWidth: 1,
            borderStyle: "solid",
            borderColor: "var(--tw-border)",
            borderRadius: "var(--tw-radius)",
            boxShadow:
              "0 12px 32px -8px color-mix(in srgb, var(--tw-ink) 22%, transparent)",
          }}
        >
          <ul className="py-1">
            {LINKS.map((l) => (
              <li key={l.href}>
                <a
                  href={l.href}
                  target={l.external ? "_blank" : undefined}
                  rel={l.external ? "noopener noreferrer" : undefined}
                  role="menuitem"
                  onClick={(e) => {
                    if (l.internal) {
                      e.preventDefault();
                      navigate(l.href);
                    }
                    setOpen(false);
                  }}
                  className="block px-3 py-2 leading-tight"
                  style={{
                    color: "var(--tw-ink)",
                    fontFamily: "var(--tw-font-body)",
                  }}
                >
                  <span className="text-sm">{l.label}</span>
                  <span
                    className="block text-[10px]"
                    style={{ color: "var(--tw-ink-dim)" }}
                  >
                    {l.hint}
                  </span>
                </a>
              </li>
            ))}
          </ul>
          <div
            className="px-3 py-2 flex items-center justify-between"
            style={{
              borderTopWidth: 1,
              borderTopStyle: "solid",
              borderTopColor: "var(--tw-border)",
            }}
          >
            <span
              className="tw-eyebrow text-[9px]"
              style={{ color: "var(--tw-ink-dim)" }}
            >
              Version
            </span>
            <code
              className="text-[11px]"
              style={{
                color: "var(--tw-ink-muted)",
                fontFamily: "var(--tw-font-mono)",
              }}
            >
              {version ?? "…"}
            </code>
          </div>
        </div>
      )}
    </div>
  );
}
