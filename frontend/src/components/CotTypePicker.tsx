import React from "react";
import { useMemo, useState } from "react";

import {
  AFFILIATIONS,
  DIMENSIONS,
  FUNCTIONS,
  MODIFIERS,
  buildCotType,
  parseCotType,
  type Choice,
} from "../cot/taxonomy";

interface Props {
  value: string;
  onChange: (cotType: string) => void;
  /** Show an "Advanced" toggle that reveals the raw input. */
  allowAdvanced?: boolean;
  /** Show step hints inline. Off by default on mobile to save vertical
   *  space; on by default on desktop. */
  showHints?: boolean;
}

/** Four-step picker for MIL-STD-2525 CoT type strings. Reusable inside
 *  any form that needs to set a target's cot_type.
 *
 *  Mobile layout: each step stacks full-width with a sticky preview
 *  band at the top. Desktop: 4 equal-width columns side by side. */
export function CotTypePicker({
  value,
  onChange,
  allowAdvanced = true,
  showHints = false,
}: Props): React.JSX.Element {
  const parsed = useMemo(() => parseCotType(value), [value]);
  const [advanced, setAdvanced] = useState(false);
  const [raw, setRaw] = useState(value);

  const fnChoices = FUNCTIONS[parsed.dimension] ?? [];
  const modKey = `${parsed.dimension}/${parsed.fn}`;
  const modChoices = MODIFIERS[modKey] ?? [];

  function emit(next: {
    affiliation?: string;
    dimension?: string;
    fn?: string;
    modifier?: string;
  }): void {
    const a = next.affiliation ?? parsed.affiliation;
    const d = next.dimension ?? parsed.dimension;
    const f = next.fn ?? parsed.fn;
    const m = next.modifier ?? parsed.modifier;
    // Changing dimension invalidates function + modifier.
    if (next.dimension !== undefined && next.dimension !== parsed.dimension) {
      onChange(buildCotType(a, d, "", ""));
      return;
    }
    // Changing function invalidates modifier.
    if (next.fn !== undefined && next.fn !== parsed.fn) {
      onChange(buildCotType(a, d, f, ""));
      return;
    }
    onChange(buildCotType(a, d, f, m));
  }

  function applyRaw(): void {
    const trimmed = raw.trim();
    if (trimmed) onChange(trimmed);
  }

  return (
    <div className="space-y-3">
      <PreviewBand value={value} />

      {advanced ? (
        <div className="space-y-2">
          <label
            htmlFor="cot-raw"
            className="tw-eyebrow text-[10px]"
            style={{ color: "var(--tw-ink-dim)" }}
          >
            Raw CoT type
          </label>
          <div className="flex gap-2">
            <input
              id="cot-raw"
              value={raw}
              onChange={(e) => setRaw(e.target.value)}
              onBlur={applyRaw}
              spellCheck={false}
              className="flex-1 px-3 py-2 text-sm"
              style={{
                background: "var(--tw-bg)",
                borderWidth: 1,
                borderStyle: "solid",
                borderColor: "var(--tw-border)",
                borderRadius: "var(--tw-radius)",
                color: "var(--tw-ink)",
                fontFamily: "var(--tw-font-mono)",
                minHeight: 44,
              }}
            />
            <button
              type="button"
              onClick={applyRaw}
              className="tw-eyebrow text-[11px] px-3"
              style={{
                background: "var(--tw-accent-bg)",
                color: "var(--tw-accent-ink)",
                borderRadius: "var(--tw-radius)",
                minHeight: 44,
              }}
            >
              Apply
            </button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 desktop:grid-cols-4 gap-3">
          <Step
            label="Affiliation"
            choices={AFFILIATIONS}
            selected={parsed.affiliation}
            onPick={(c) => emit({ affiliation: c })}
            showHint={showHints}
          />
          <Step
            label="Dimension"
            choices={DIMENSIONS}
            selected={parsed.dimension}
            disabled={!parsed.affiliation}
            onPick={(c) => emit({ dimension: c })}
            showHint={showHints}
          />
          <Step
            label="Function"
            choices={fnChoices}
            selected={parsed.fn}
            disabled={!parsed.dimension}
            onPick={(c) => emit({ fn: c })}
            showHint={showHints}
            emptyHint="Pick a dimension to see functions"
          />
          <Step
            label="Modifier"
            choices={modChoices}
            selected={parsed.modifier}
            disabled={!parsed.fn || modChoices.length === 0}
            onPick={(c) => emit({ modifier: c })}
            showHint={showHints}
            emptyHint="No modifiers for this function"
            optional
          />
        </div>
      )}

      {allowAdvanced && (
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => {
              setRaw(value);
              setAdvanced((v) => !v);
            }}
            className="tw-eyebrow text-[10px] px-3 py-1"
            style={{ color: "var(--tw-ink-dim)" }}
          >
            {advanced ? "← Use guided picker" : "Advanced (raw CoT) →"}
          </button>
        </div>
      )}
    </div>
  );
}

function PreviewBand({ value }: { value: string }): React.JSX.Element {
  const { affiliation, dimension, fn, modifier } = parseCotType(value);
  const a = AFFILIATIONS.find((c) => c.code === affiliation);
  const d = DIMENSIONS.find((c) => c.code === dimension);
  const f = (FUNCTIONS[dimension] ?? []).find((c) => c.code === fn);
  const mods = (MODIFIERS[`${dimension}/${fn}`] ?? []).find(
    (c) => c.code === modifier,
  );
  const parts: string[] = [];
  if (a) parts.push(a.label);
  if (d) parts.push(d.label);
  if (f) parts.push(f.label);
  if (mods) parts.push(mods.label);
  return (
    <div
      className="px-3 py-2 flex flex-col gap-1 sticky top-0 z-10"
      style={{
        background: "var(--tw-bg-panel)",
        borderWidth: 1,
        borderStyle: "solid",
        borderColor: "var(--tw-border)",
        borderRadius: "var(--tw-radius)",
      }}
    >
      <code
        className="text-[15px] tracking-wider"
        style={{
          color: "var(--tw-accent)",
          fontFamily: "var(--tw-font-mono)",
        }}
      >
        {value || "—"}
      </code>
      <span
        className="text-[11px]"
        style={{
          color: "var(--tw-ink-dim)",
          fontFamily: "var(--tw-font-body)",
        }}
      >
        {parts.length > 0 ? parts.join(" · ") : "incomplete"}
      </span>
    </div>
  );
}

function Step({
  label,
  choices,
  selected,
  onPick,
  disabled = false,
  showHint = false,
  emptyHint,
  optional = false,
}: {
  label: string;
  choices: readonly Choice[];
  selected: string;
  onPick: (code: string) => void;
  disabled?: boolean;
  showHint?: boolean;
  emptyHint?: string;
  optional?: boolean;
}): React.JSX.Element {
  return (
    <fieldset
      className="space-y-2"
      style={{ opacity: disabled ? 0.5 : 1, pointerEvents: disabled ? "none" : "auto" }}
    >
      <legend
        className="tw-eyebrow text-[10px] flex items-baseline gap-2"
        style={{ color: "var(--tw-ink-dim)" }}
      >
        {label}
        {optional && (
          <span className="text-[9px]" style={{ color: "var(--tw-ink-dim)" }}>
            (optional)
          </span>
        )}
      </legend>
      {choices.length === 0 ? (
        <p
          className="text-[11px] italic px-2"
          style={{ color: "var(--tw-ink-dim)" }}
        >
          {emptyHint ?? "—"}
        </p>
      ) : (
        <div className="flex flex-col gap-1">
          {choices.map((c) => {
            const active = c.code === selected;
            return (
              <button
                key={c.code}
                type="button"
                onClick={() => onPick(c.code)}
                aria-pressed={active}
                className="text-left px-3 py-2 leading-tight"
                style={{
                  background: active
                    ? "var(--tw-accent-bg)"
                    : "var(--tw-bg)",
                  color: active ? "var(--tw-accent-ink)" : "var(--tw-ink)",
                  borderWidth: 1,
                  borderStyle: "solid",
                  borderColor: active
                    ? "var(--tw-accent)"
                    : "var(--tw-border)",
                  borderRadius: "var(--tw-radius)",
                  fontFamily: "var(--tw-font-body)",
                  minHeight: 44,
                }}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-sm font-medium">{c.label}</span>
                  <code
                    className="text-[10px]"
                    style={{
                      color: active ? "var(--tw-accent-ink)" : "var(--tw-ink-dim)",
                      fontFamily: "var(--tw-font-mono)",
                    }}
                  >
                    {c.code}
                  </code>
                </div>
                {showHint && c.hint && (
                  <p
                    className="text-[10px] mt-0.5"
                    style={{
                      color: active
                        ? "var(--tw-accent-ink)"
                        : "var(--tw-ink-dim)",
                    }}
                  >
                    {c.hint}
                  </p>
                )}
              </button>
            );
          })}
        </div>
      )}
    </fieldset>
  );
}
