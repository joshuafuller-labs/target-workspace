import React from "react";

import { ageDisplay } from "../age";
import { useNow } from "../useNow";

interface Props {
  observedAtIso: string;
  /** When true, the counter renders inside a brief pulsing halo for ~5s
   *  to draw the eye to a newly-arrived observation. The pulse signals
   *  arrival, not freshness — freshness is encoded in the counter color. */
  flash?: boolean;
  /** Slightly larger variant for use in modals / edit pages. */
  size?: "sm" | "md";
}

/** Per-target ticking age counter. Replaces the old static "LIVE / 3m /
 *  47m" badge per tw-ced: counter answers "how old?", color answers
 *  "should I act?", pulse answers "did something just change?". */
export function AgeCounter({
  observedAtIso,
  flash = false,
  size = "sm",
}: Props): React.JSX.Element {
  const now = useNow();
  const { text, colorVar } = ageDisplay(observedAtIso, now);
  return (
    <span
      className="inline-flex items-center gap-1"
      title={`observed ${new Date(observedAtIso).toLocaleString()}`}
      style={{
        color: `var(${colorVar})`,
        fontFamily: "var(--tw-font-mono)",
        fontVariantNumeric: "tabular-nums",
        fontSize: size === "md" ? 13 : 11,
        letterSpacing: "0.02em",
        lineHeight: 1,
      }}
    >
      <span
        aria-hidden
        className={flash ? "tw-pulse" : undefined}
        style={{
          width: size === "md" ? 8 : 6,
          height: size === "md" ? 8 : 6,
          borderRadius: 999,
          background: `var(${colorVar})`,
          boxShadow: flash ? `0 0 8px var(${colorVar})` : undefined,
          display: "inline-block",
          flex: "none",
        }}
      />
      <span>{text}</span>
    </span>
  );
}
