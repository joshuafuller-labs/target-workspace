import React from "react";
import { useEffect, useState } from "react";

interface Props {
  /** Stable id so this hint can be dismissed independently. */
  id: string;
  /** Short headline shown above the body. */
  title: string;
  /** Body text — keep it terse, one or two sentences. */
  children: React.ReactNode;
}

const STORAGE_PREFIX = "tw.onboarding.hint.";
const GLOBAL_KEY = "tw.onboarding.hints.disabled";

function key(id: string): string {
  return `${STORAGE_PREFIX}${id}`;
}

function isDismissed(id: string): boolean {
  if (typeof window === "undefined") return true;
  try {
    if (window.localStorage.getItem(GLOBAL_KEY) === "1") return true;
    return window.localStorage.getItem(key(id)) === "1";
  } catch {
    return true;
  }
}

/** In-context onboarding hint (tw-dqjx).
 *
 *  Dismissed-state lives in localStorage so the same workspace+user
 *  doesn't see a hint twice. Settings → Profile carries the global
 *  toggle that hides every hint at once.
 */
export function HintCard({ id, title, children }: Props): React.JSX.Element | null {
  const [dismissed, setDismissed] = useState<boolean>(() => isDismissed(id));

  // Re-check on mount in case the global toggle changed in another tab.
  useEffect(() => {
    setDismissed(isDismissed(id));
  }, [id]);

  if (dismissed) return null;

  function dismiss(): void {
    try {
      window.localStorage.setItem(key(id), "1");
    } catch {
      // ignore — best-effort
    }
    setDismissed(true);
  }

  return (
    <aside
      role="note"
      className="rounded p-3 text-sm"
      style={{
        background: "var(--tw-bg-panel)",
        borderWidth: 1,
        borderStyle: "solid",
        borderColor: "var(--tw-accent)",
        color: "var(--tw-ink)",
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p
            className="tw-eyebrow text-[10px] mb-1"
            style={{ color: "var(--tw-accent)" }}
          >
            Tip · {title}
          </p>
          <div style={{ color: "var(--tw-ink-muted)" }}>{children}</div>
        </div>
        <button
          type="button"
          onClick={dismiss}
          aria-label="Dismiss tip"
          className="text-xs px-2 py-1"
          style={{
            color: "var(--tw-ink-dim)",
            background: "transparent",
            border: "none",
            cursor: "pointer",
          }}
        >
          Got it
        </button>
      </div>
    </aside>
  );
}

/** Helper: toggle the global "no hints" preference. SettingsPage uses
 *  this to expose the master switch. */
export function setHintsGloballyDisabled(disabled: boolean): void {
  try {
    if (disabled) window.localStorage.setItem(GLOBAL_KEY, "1");
    else window.localStorage.removeItem(GLOBAL_KEY);
  } catch {
    // ignore
  }
}

export function areHintsGloballyDisabled(): boolean {
  try {
    return window.localStorage.getItem(GLOBAL_KEY) === "1";
  } catch {
    return false;
  }
}
