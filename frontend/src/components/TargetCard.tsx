import React from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import { trackStateOf } from "../track_state";
import type { Board, Target } from "../types";
import { useNow } from "../useNow";
import { AgeCounter } from "./AgeCounter";

interface Props {
  target: Target;
  board: Board;
  onClick: () => void;
  // Set on the floating preview rendered inside DragOverlay so it doesn't
  // re-register as a draggable and doesn't dim itself.
  asOverlay?: boolean;
  /** Pulse the age counter for ~5s when this id was just observed.
   *  Driven by realtime target.created / target.updated events at the
   *  BoardView level — see recentlyUpdatedIds. */
  flash?: boolean;
}

export function TargetCard({
  target,
  board,
  onClick,
  asOverlay = false,
  flash = false,
}: Props): React.JSX.Element {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({
      id: target.id,
      data: { type: "target", target },
      disabled: asOverlay,
    });

  // The original card dims while being dragged; the floating overlay is
  // the visible representation. Sortable also adds a transform so the
  // card slides into its new spot during the drag.
  const opacity = isDragging && !asOverlay ? 0.3 : 1;
  const sortableStyle = asOverlay
    ? undefined
    : { transform: CSS.Transform.toString(transform), transition };

  return (
    <button
      ref={asOverlay ? undefined : setNodeRef}
      onClick={(e) => {
        // Suppress click immediately after a drag — dnd-kit fires onClick
        // even after a successful drop in some browsers.
        if (isDragging) return;
        e.stopPropagation();
        onClick();
      }}
      // Spread drag listeners onto the card; activationConstraint at the
      // sensor level keeps quick clicks from registering as drags.
      {...listeners}
      {...attributes}
      className="w-full text-left p-3 transition-colors"
      style={{
        ...sortableStyle,
        background: "var(--tw-bg-panel)",
        borderWidth: 1,
        borderStyle: "solid",
        borderColor: "var(--tw-border)",
        borderRadius: "var(--tw-radius)",
        color: "var(--tw-ink)",
        fontFamily: "var(--tw-font-body)",
        opacity,
        cursor: asOverlay ? "grabbing" : "grab",
        touchAction: "none",
        minHeight: 44,
        boxShadow: asOverlay
          ? "0 10px 30px rgba(0,0,0,0.55), 0 0 0 1px var(--tw-accent)"
          : undefined,
      }}
    >
      <div className="flex items-baseline justify-between gap-2">
        <div
          className="text-sm font-semibold truncate"
          style={{ fontFamily: "var(--tw-font-mono)" }}
        >
          {target.name}
        </div>
        <div
          className="text-[10px]"
          style={{
            color: "var(--tw-ink-dim)",
            fontFamily: "var(--tw-font-mono)",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          v{target.version}
        </div>
      </div>
      <div
        className="text-[10px] mt-1"
        style={{
          color: "var(--tw-ink-dim)",
          fontFamily: "var(--tw-font-mono)",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {target.lat.toFixed(4)}, {target.lon.toFixed(4)}
      </div>
      <div className="flex items-center gap-1 mt-2 flex-wrap">
        <ChipDim>{target.cot_type}</ChipDim>
        {target.confidence !== null && (
          <ChipDim>conf {target.confidence.toFixed(2)}</ChipDim>
        )}
        <QualityChip quality={target.geometry_quality} />
        <TrackStateChip observedAtIso={target.time} />
        {target.custom_fields?.entity_kind === "hazard" && <HazardChip />}
      </div>
      <div
        className="flex items-center gap-2 mt-2 text-[10px]"
        style={{
          fontFamily: "var(--tw-font-mono)",
          fontVariantNumeric: "tabular-nums",
        }}
      >
        <AgeCounter observedAtIso={target.time} flash={flash} />
        <span style={{ color: "var(--tw-ink-dim)" }} className="truncate">
          {new Date(target.time).toLocaleString()}
        </span>
      </div>
      <div className="sr-only">{`On board ${board.name}`}</div>
    </button>
  );
}

function HazardChip(): React.JSX.Element {
  return (
    <span
      className="tw-eyebrow inline-flex items-center px-1.5 py-0.5 text-[9px]"
      title="hazard · obstacle convention (tw-49a)"
      style={{
        color: "var(--tw-approval)",
        borderColor: "var(--tw-approval)",
        borderWidth: 1,
        borderStyle: "solid",
        borderRadius: "calc(var(--tw-radius) * 0.6)",
        letterSpacing: "0.14em",
      }}
    >
      ⚠ HAZARD
    </span>
  );
}

function QualityChip({
  quality,
}: {
  quality: import("../types").GeometryQuality;
}): React.JSX.Element {
  // Color the chip by RoE eligibility — bearing-only / single-source draw
  // warning-color (approval), corroborated draws accent, confirmed draws
  // bright accent. Maps to docs/research/ukraine-fires-targeting.md §5.
  const isWarn = quality === "bearing-only" || quality === "single-source";
  const colorVar = isWarn ? "--tw-approval" : "--tw-accent";
  const labelMap: Record<string, string> = {
    "bearing-only": "LOB",
    "single-source": "1-src",
    corroborated: "corrob",
    confirmed: "conf'd",
  };
  return (
    <span
      className="tw-eyebrow inline-flex items-center px-1.5 py-0.5 text-[9px]"
      title={`geometry quality: ${quality}`}
      style={{
        color: `var(${colorVar})`,
        borderColor: `var(${colorVar})`,
        borderWidth: 1,
        borderStyle: "solid",
        borderRadius: "calc(var(--tw-radius) * 0.6)",
        letterSpacing: "0.14em",
      }}
    >
      {labelMap[quality] ?? quality}
    </span>
  );
}

function TrackStateChip({
  observedAtIso,
}: {
  observedAtIso: string;
}): React.JSX.Element | null {
  // Subscribe to the shared 1Hz clock so the chip flips from active →
  // coasting → stale → lost as time advances without needing the parent
  // to re-render. Cheap — useSyncExternalStore is a noop when the value
  // hasn't crossed a threshold.
  const now = useNow();
  // Active is the default / steady state — no chip needed; only surface
  // the chip when the track has degraded (coasting / stale / lost).
  const s = trackStateOf(observedAtIso, new Date(now));
  if (s.state === "active") return null;
  const border =
    s.treatment === "dashed" ? "dashed" : s.treatment === "crosshatch" ? "double" : "solid";
  return (
    <span
      className="tw-eyebrow inline-flex items-center px-1.5 py-0.5 text-[9px]"
      title={`track state: ${s.state}`}
      style={{
        color: `var(${s.colorVar})`,
        borderColor: `var(${s.colorVar})`,
        borderWidth: s.treatment === "crosshatch" ? 3 : 1,
        borderStyle: border,
        borderRadius: "calc(var(--tw-radius) * 0.6)",
        letterSpacing: "0.14em",
        opacity: s.treatment === "dim" ? 0.65 : 1,
      }}
    >
      {s.label}
    </span>
  );
}

function ChipDim({ children }: { children: React.ReactNode }): React.JSX.Element {
  return (
    <span
      className="tw-eyebrow inline-flex items-center px-1.5 py-0.5 text-[9px]"
      style={{
        background: "color-mix(in srgb, var(--tw-bg-panel) 65%, var(--tw-border) 35%)",
        color: "var(--tw-ink-muted)",
        borderRadius: "calc(var(--tw-radius) * 0.6)",
        letterSpacing: "0.14em",
      }}
    >
      {children}
    </span>
  );
}
