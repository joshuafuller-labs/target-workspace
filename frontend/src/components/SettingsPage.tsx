import React from "react";
import { useEffect, useState } from "react";

import { api } from "../api";
import { BRAND_NAME } from "../brand";
import { navigate } from "../router";
import { applyTheme } from "../theme";
import type {
  Board,
  PluginCatalog,
  PublisherConfig,
  PublisherConfigPayload,
  SourceConfig,
  SourceConfigPayload,
  ThemeName,
  UserOut,
} from "../types";
import { AccountSecurityContent } from "./AccountSecurityPage";
import {
  areHintsGloballyDisabled,
  setHintsGloballyDisabled,
} from "./HintCard";
import { UserAdminPanel } from "./UserAdminPanel";

const THEME_OPTIONS: ReadonlyArray<{
  name: ThemeName;
  title: string;
  hint: string;
}> = [
  {
    name: "neutral",
    title: "Neutral",
    hint: "Editorial baseline; appropriate for civilian / corporate workspaces.",
  },
  {
    name: "tactical",
    title: "Tactical",
    hint: "ATAK / Toughbook aesthetic — high contrast, mono display.",
  },
  {
    name: "federal",
    title: "Federal",
    hint: "Government precision — navy + federal gold.",
  },
  {
    name: "sar",
    title: "SAR",
    hint: "Search-and-rescue / outdoor ops — high-vis orange.",
  },
  {
    name: "ics",
    title: "ICS",
    hint: "Incident Command System — FEMA / EOC operations.",
  },
];

type Tab =
  | "general"
  | "security"
  | "users"
  | "theme"
  | "freshness"
  | "correlation"
  | "sources"
  | "publishers"
  | "profile";

interface TabSpec {
  key: Tab;
  label: string;
  /** Optional minimum role to see the tab. Backend gates the API
   *  anyway; hiding the tab keeps non-admins from a 403 dead-end. */
  minRole?: string;
}

const ALL_TABS: ReadonlyArray<TabSpec> = [
  { key: "general", label: "General" },
  { key: "security", label: "Account & Security" },
  { key: "users", label: "Users", minRole: "commander" },
  { key: "theme", label: "Theme" },
  { key: "freshness", label: "Freshness" },
  { key: "correlation", label: "Correlation" },
  { key: "sources", label: "Sources", minRole: "admin" },
  { key: "publishers", label: "Publishers", minRole: "admin" },
  { key: "profile", label: "Profile" },
];

const ROLE_RANK: Record<string, number> = {
  viewer: 0,
  observer: 1,
  operator: 2,
  approver: 3,
  commander: 4,
  admin: 5,
};

function visibleTabs(role: string): TabSpec[] {
  const rank = ROLE_RANK[role] ?? 0;
  return ALL_TABS.filter(
    (t) => t.minRole === undefined || (ROLE_RANK[t.minRole] ?? 99) <= rank,
  );
}

interface Props {
  user: UserOut;
}

/** Workspace settings page at `/settings`. First cut is mostly
 *  inspection — the underlying knobs (brand name, freshness windows,
 *  correlation tolerances) are currently env-vars or per-board state.
 *  Mutation endpoints land with their own bds; this page makes the
 *  current config visible. */
export function SettingsPage({ user }: Props): React.JSX.Element {
  const [tab, setTab] = useState<Tab>("general");
  const [boards, setBoards] = useState<Board[]>([]);
  const [previewTheme, setPreviewTheme] = useState<ThemeName | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        setBoards(await api.listBoards());
      } catch {
        // boards are optional for settings inspection
      }
    })();
  }, []);

  // Single source of truth for which theme is currently painted:
  // hover/focus preview wins, otherwise the saved theme of the first
  // board. Avoid the cleanup-pattern variant — it runs with stale
  // closure values and races onCommit, which produced the
  // "click-reverts-to-previous-theme" flake.
  useEffect(() => {
    const next = previewTheme ?? boards[0]?.theme;
    if (next) applyTheme(next);
  }, [previewTheme, boards]);

  return (
    <main
      className="min-h-screen"
      style={{ background: "var(--tw-bg)", color: "var(--tw-ink)" }}
    >
      <header
        className="tw-rail px-4 desktop:px-6 py-3 border-b sticky top-0 z-20 flex items-center gap-3"
        style={{
          background: "var(--tw-bg-panel)",
          borderColor: "var(--tw-border)",
        }}
      >
        <button
          onClick={() => navigate("/")}
          className="tw-eyebrow text-[11px] px-3"
          style={{
            background: "transparent",
            borderWidth: 1,
            borderStyle: "solid",
            borderColor: "var(--tw-border)",
            borderRadius: "var(--tw-radius)",
            color: "var(--tw-ink-muted)",
            minHeight: 44,
          }}
        >
          ← Board
        </button>
        <div className="flex-1">
          <p
            className="tw-eyebrow text-[10px]"
            style={{ color: "var(--tw-brand)" }}
          >
            {BRAND_NAME}
          </p>
          <h1 className="tw-display text-lg desktop:text-xl">Settings</h1>
        </div>
        <code
          className="hidden desktop:block text-[10px]"
          style={{
            color: "var(--tw-ink-dim)",
            fontFamily: "var(--tw-font-mono)",
          }}
        >
          {user.email} · {user.role}
        </code>
      </header>

      {/* Mobile: top-level segmented control. Desktop: same row of pills. */}
      <nav
        className="px-4 desktop:px-6 py-3 flex gap-2 overflow-x-auto"
        style={{
          background: "var(--tw-bg-panel)",
          borderBottomWidth: 1,
          borderBottomStyle: "solid",
          borderBottomColor: "var(--tw-border)",
        }}
        aria-label="Settings sections"
      >
        {visibleTabs(user.role).map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            aria-pressed={tab === t.key}
            className="tw-eyebrow text-[11px] px-3 whitespace-nowrap"
            style={{
              background:
                tab === t.key ? "var(--tw-accent-bg)" : "transparent",
              color:
                tab === t.key ? "var(--tw-accent-ink)" : "var(--tw-ink-muted)",
              borderWidth: 1,
              borderStyle: "solid",
              borderColor:
                tab === t.key ? "var(--tw-accent)" : "var(--tw-border)",
              borderRadius: "var(--tw-radius)",
              minHeight: 44,
            }}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <div className="max-w-3xl mx-auto px-4 desktop:px-6 py-6 space-y-4">
        {tab === "general" && <GeneralPanel boardCount={boards.length} />}
        {tab === "security" && <AccountSecurityContent user={user} />}
        {tab === "users" && <UserAdminPanel me={user} />}
        {tab === "theme" && (
          <ThemePanel
            currentBoardId={boards[0]?.id ?? null}
            current={boards[0]?.theme ?? "neutral"}
            onPreview={setPreviewTheme}
            onCommit={async (name) => {
              const id = boards[0]?.id;
              if (!id) return;
              const updated = await api.updateBoard(id, { theme: name });
              setBoards((prev) => {
                const next = [...prev];
                if (next[0]) next[0] = { ...next[0], theme: updated.theme };
                return next;
              });
              setPreviewTheme(null);
            }}
          />
        )}
        {tab === "freshness" && <FreshnessPanel />}
        {tab === "correlation" && <CorrelationPanel />}
        {tab === "sources" && <SourcesPanel />}
        {tab === "publishers" && <PublishersPanel />}
        {tab === "profile" && <ProfilePanel />}
      </div>
    </main>
  );
}

function ProfilePanel(): React.JSX.Element {
  const [disabled, setDisabled] = useState<boolean>(() =>
    areHintsGloballyDisabled(),
  );
  function toggle(): void {
    const next = !disabled;
    setHintsGloballyDisabled(next);
    setDisabled(next);
  }
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">Profile preferences</h2>
      <p style={{ color: "var(--tw-ink-muted)" }} className="text-sm">
        Onboarding hints appear inline the first time you reach a screen.
        Toggle them all off here.
      </p>
      <label className="flex items-center gap-3 text-sm">
        <input type="checkbox" checked={disabled} onChange={toggle} />
        Hide onboarding hints
      </label>
    </section>
  );
}

function GeneralPanel({ boardCount }: { boardCount: number }): React.JSX.Element {
  const [brand, setBrand] = useState<string>("");
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const ws = await api.getWorkspace();
        if (cancelled) return;
        setBrand(ws.brand_name ?? "");
        setLoaded(true);
      } catch (e) {
        if (!cancelled) setError(String((e as Error).message ?? e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function save(): Promise<void> {
    setSaving(true);
    setError(null);
    try {
      await api.patchWorkspace({ brand_name: brand || null });
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Panel title="Workspace">
      <Row
        label="Brand name"
        hint="Workspace-wide product name (overrides the VITE_BRAND_NAME build default for the SPA shell)."
      >
        <div className="flex gap-2 w-full">
          <input
            value={brand}
            onChange={(e) => setBrand(e.target.value)}
            placeholder={BRAND_NAME}
            disabled={!loaded || saving}
            className="flex-1 px-2 py-1 text-sm"
            style={{
              background: "var(--tw-bg)",
              color: "var(--tw-ink)",
              borderWidth: 1,
              borderStyle: "solid",
              borderColor: "var(--tw-border)",
              borderRadius: "var(--tw-radius)",
            }}
          />
          <button
            type="button"
            onClick={save}
            disabled={!loaded || saving}
            className="px-3 py-1 text-sm"
            style={{
              background: "var(--tw-accent-bg)",
              color: "var(--tw-accent-ink)",
              border: "none",
              borderRadius: "var(--tw-radius)",
            }}
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </Row>
      <Row label="Boards" hint="Boards visible to this workspace.">
        <code style={mono}>{boardCount}</code>
      </Row>
      {error && (
        <Row label="Error">
          <span style={{ color: "var(--tw-approval)" }}>{error}</span>
        </Row>
      )}
    </Panel>
  );
}

function ThemePanel({
  currentBoardId,
  current,
  onPreview,
  onCommit,
}: {
  currentBoardId: string | null;
  current: ThemeName;
  onPreview: (t: ThemeName | null) => void;
  onCommit: (name: ThemeName) => Promise<void>;
}): React.JSX.Element {
  const [busy, setBusy] = useState<ThemeName | null>(null);
  const [error, setError] = useState<string | null>(null);
  const disabled = currentBoardId === null;
  return (
    <Panel
      title="Theme"
      hint={
        disabled
          ? "Create a board first to set a theme."
          : "Hover a tile to preview, click to commit. Applies to the first board."
      }
    >
      <div className="grid grid-cols-1 desktop:grid-cols-2 gap-3">
        {THEME_OPTIONS.map((opt) => {
          const active = opt.name === current;
          return (
            <button
              key={opt.name}
              type="button"
              disabled={disabled || busy !== null}
              onMouseEnter={() => onPreview(opt.name)}
              onFocus={() => onPreview(opt.name)}
              onMouseLeave={() => onPreview(null)}
              onBlur={() => onPreview(null)}
              onClick={async () => {
                if (disabled || active) return;
                setBusy(opt.name);
                setError(null);
                try {
                  await onCommit(opt.name);
                } catch (e) {
                  setError(e instanceof Error ? e.message : String(e));
                } finally {
                  setBusy(null);
                }
              }}
              className="text-left px-3 py-3"
              style={{
                background: active ? "var(--tw-accent-bg)" : "var(--tw-bg)",
                color: active ? "var(--tw-accent-ink)" : "var(--tw-ink)",
                borderWidth: 1,
                borderStyle: "solid",
                borderColor: active
                  ? "var(--tw-accent)"
                  : "var(--tw-border)",
                borderRadius: "var(--tw-radius)",
                minHeight: 64,
              }}
            >
              <div className="flex items-baseline justify-between">
                <span className="text-sm font-medium">{opt.title}</span>
                {active && (
                  <span
                    className="tw-eyebrow text-[9px]"
                    style={{ color: "var(--tw-accent-ink)" }}
                  >
                    {busy === opt.name ? "Saving…" : "Current"}
                  </span>
                )}
              </div>
              <p
                className="text-[11px] mt-1"
                style={{
                  color: active ? "var(--tw-accent-ink)" : "var(--tw-ink-dim)",
                }}
              >
                {opt.hint}
              </p>
            </button>
          );
        })}
      </div>
      {error && (
        <p
          className="text-sm px-3 py-2 mt-3"
          style={{
            background: "var(--tw-bg-panel)",
            borderLeftWidth: 3,
            borderLeftStyle: "solid",
            borderLeftColor: "var(--tw-approval)",
            color: "var(--tw-approval)",
          }}
        >
          Could not save theme: {error}
        </p>
      )}
    </Panel>
  );
}

function FreshnessPanel(): React.JSX.Element {
  return (
    <>
      <Panel
        title="Age counter colors"
        hint="The age counter on each TargetCard ticks every second; the color crosses these thresholds as time passes. Use the fresh: filter prefix to query by bucket. Tuneable per workspace (tw-smc follow-up)."
      >
        <Row label="live" hint="fresh:live — accent color, just observed.">
          <code style={mono}>&lt; 60 s</code>
        </Row>
        <Row label="recent" hint="fresh:recent — accent color holds.">
          <code style={mono}>&lt; 5 m</code>
        </Row>
        <Row label="warm" hint="fresh:warm — approval/amber.">
          <code style={mono}>&lt; 15 m</code>
        </Row>
        <Row label="stale" hint="fresh:stale — dim. Needs re-observation.">
          <code style={mono}>&gt;= 15 m</code>
        </Row>
      </Panel>
      <Panel
        title="Track state thresholds"
        hint="Track state is a stronger claim than freshness — it answers 'do we still believe the propagated position?'. Map renders coasting at lower alpha, stale dimmer, lost barely visible."
      >
        <Row label="active" hint="Recent observation; position trusted.">
          <code style={mono}>&lt; 5 m</code>
        </Row>
        <Row label="coasting" hint="No recent obs; last-known propagated.">
          <code style={mono}>&lt; 30 m</code>
        </Row>
        <Row label="stale" hint="Needs re-observation.">
          <code style={mono}>&lt; 90 m</code>
        </Row>
        <Row label="lost" hint="Treat as gone unless re-acquired.">
          <code style={mono}>&gt;= 90 m</code>
        </Row>
      </Panel>
    </>
  );
}

function CorrelationPanel(): React.JSX.Element {
  return (
    <Panel
      title="Track correlation"
      hint="When a new fix arrives, it folds into an existing track if it's within both windows. Avoids duplicate cards per moving contact."
    >
      <Row label="Distance" hint="Haversine, meters.">
        <code style={mono}>500 m</code>
      </Row>
      <Row label="Time" hint="Window for re-observation merge.">
        <code style={mono}>30 m</code>
      </Row>
      <Row label="Affiliation" hint="Must match for correlation to fire.">
        <code style={mono}>identical</code>
      </Row>
    </Panel>
  );
}

function SourcesPanel(): React.JSX.Element {
  const [catalog, setCatalog] = useState<PluginCatalog | null>(null);
  const [sources, setSources] = useState<SourceConfig[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [pluginType, setPluginType] = useState("manual");
  const [enabled, setEnabled] = useState(true);
  const [adapterConfig, setAdapterConfig] = useState("{}");
  const [normalizationMap, setNormalizationMap] = useState('{"name":"$.callsign"}');
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void refreshSourceState();
  }, []);

  async function refreshSourceState(nextSelectedId?: string | null): Promise<void> {
    const [plugins, rows] = await Promise.all([api.listPlugins(), api.listSources()]);
    setCatalog(plugins);
    setSources(rows);
    const selected =
      rows.find((row) => row.id === nextSelectedId) ??
      rows.find((row) => row.id === selectedId) ??
      rows[0] ??
      null;
    loadSource(selected, plugins);
  }

  function loadSource(row: SourceConfig | null, plugins = catalog): void {
    setSelectedId(row?.id ?? null);
    setName(row?.name ?? "");
    setPluginType(row?.plugin_type ?? plugins?.sources[0]?.name ?? "manual");
    setEnabled(row?.enabled ?? true);
    setAdapterConfig(JSON.stringify(row?.adapter_config ?? {}, null, 2));
    setNormalizationMap(
      JSON.stringify(row?.normalization_map ?? { name: "$.callsign" }, null, 2),
    );
    setMessage(null);
  }

  function sourcePayload(): SourceConfigPayload {
    return {
      name,
      plugin_type: pluginType,
      enabled,
      adapter_config: parseJsonObject(adapterConfig, "Adapter config"),
      normalization_map: parseJsonObject(normalizationMap, "Normalization map"),
      promotion_policy_id: null,
    };
  }

  async function save(create: boolean): Promise<void> {
    setBusy(true);
    setMessage(null);
    try {
      const payload = sourcePayload();
      const saved =
        create || selectedId === null
          ? await api.createSource(payload)
          : await api.updateSource(selectedId, payload);
      await refreshSourceState(saved.id);
      setMessage(create ? "Source created." : "Source updated.");
    } catch (e) {
      setMessage(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove(): Promise<void> {
    if (!selectedId) return;
    setBusy(true);
    setMessage(null);
    try {
      await api.deleteSource(selectedId);
      await refreshSourceState(null);
      setMessage("Source deleted.");
    } catch (e) {
      setMessage(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function probe(): Promise<void> {
    if (!selectedId) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await api.testSource(selectedId, {
        callsign: "ALPHA-1",
        location: { lat: 30, lon: -97 },
      });
      setMessage(`Normalized ${JSON.stringify(result.normalized)}`);
    } catch (e) {
      setMessage(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Sources">
      <ConfigList
        rows={sources.map((row) => ({
          id: row.id,
          name: row.name,
          pluginType: row.plugin_type,
          enabled: row.enabled,
        }))}
        selectedId={selectedId}
        onSelect={(id) => loadSource(sources.find((row) => row.id === id) ?? null)}
      />
      <PluginFormGrid>
        <LabeledInput label="Source name">
          <input
            aria-label="Source name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="px-2 py-2 text-sm"
            style={fieldStyle}
          />
        </LabeledInput>
        <LabeledInput label="Source plugin">
          <select
            aria-label="Source plugin"
            value={pluginType}
            onChange={(e) => setPluginType(e.target.value)}
            className="px-2 py-2 text-sm"
            style={fieldStyle}
          >
            {(catalog?.sources ?? []).map((plugin) => (
              <option key={plugin.name} value={plugin.name}>
                {plugin.name}
              </option>
            ))}
          </select>
        </LabeledInput>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          Enabled
        </label>
      </PluginFormGrid>
      <JsonField
        label="Adapter config"
        value={adapterConfig}
        onChange={setAdapterConfig}
      />
      <JsonField
        label="Normalization map"
        value={normalizationMap}
        onChange={setNormalizationMap}
      />
      <ActionRow>
        <button type="button" disabled={busy} onClick={() => void save(false)}>
          Update source
        </button>
        <button type="button" disabled={busy} onClick={() => void save(true)}>
          Create source
        </button>
        <button type="button" disabled={busy || !selectedId} onClick={() => void probe()}>
          Test source
        </button>
        <button type="button" disabled={busy || !selectedId} onClick={() => void remove()}>
          Delete source
        </button>
      </ActionRow>
      {message && <StatusLine>{message}</StatusLine>}
    </Panel>
  );
}

function PublishersPanel(): React.JSX.Element {
  const [catalog, setCatalog] = useState<PluginCatalog | null>(null);
  const [publishers, setPublishers] = useState<PublisherConfig[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [pluginType, setPluginType] = useState("raw_cot");
  const [enabled, setEnabled] = useState(true);
  const [adapterConfig, setAdapterConfig] = useState("{}");
  const [columnFilterIds, setColumnFilterIds] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void refreshPublisherState();
  }, []);

  async function refreshPublisherState(nextSelectedId?: string | null): Promise<void> {
    const [plugins, rows] = await Promise.all([api.listPlugins(), api.listPublishers()]);
    setCatalog(plugins);
    setPublishers(rows);
    const selected =
      rows.find((row) => row.id === nextSelectedId) ??
      rows.find((row) => row.id === selectedId) ??
      rows[0] ??
      null;
    loadPublisher(selected, plugins);
  }

  function loadPublisher(row: PublisherConfig | null, plugins = catalog): void {
    setSelectedId(row?.id ?? null);
    setName(row?.name ?? "");
    setPluginType(row?.plugin_type ?? plugins?.publishers[0]?.name ?? "raw_cot");
    setEnabled(row?.enabled ?? true);
    setAdapterConfig(JSON.stringify(row?.adapter_config ?? {}, null, 2));
    setColumnFilterIds((row?.column_filter_ids ?? []).join("\n"));
    setMessage(null);
  }

  function publisherPayload(): PublisherConfigPayload {
    return {
      name,
      plugin_type: pluginType,
      enabled,
      adapter_config: parseJsonObject(adapterConfig, "Adapter config"),
      column_filter_ids: columnFilterIds
        .split(/\s+/)
        .map((value) => value.trim())
        .filter(Boolean),
    };
  }

  async function save(create: boolean): Promise<void> {
    setBusy(true);
    setMessage(null);
    try {
      const payload = publisherPayload();
      const saved =
        create || selectedId === null
          ? await api.createPublisher(payload)
          : await api.updatePublisher(selectedId, payload);
      await refreshPublisherState(saved.id);
      setMessage(create ? "Publisher created." : "Publisher updated.");
    } catch (e) {
      setMessage(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove(): Promise<void> {
    if (!selectedId) return;
    setBusy(true);
    setMessage(null);
    try {
      await api.deletePublisher(selectedId);
      await refreshPublisherState(null);
      setMessage("Publisher deleted.");
    } catch (e) {
      setMessage(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Publishers">
      <ConfigList
        rows={publishers.map((row) => ({
          id: row.id,
          name: row.name,
          pluginType: row.plugin_type,
          enabled: row.enabled,
        }))}
        selectedId={selectedId}
        onSelect={(id) =>
          loadPublisher(publishers.find((row) => row.id === id) ?? null)
        }
      />
      <PluginFormGrid>
        <LabeledInput label="Publisher name">
          <input
            aria-label="Publisher name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="px-2 py-2 text-sm"
            style={fieldStyle}
          />
        </LabeledInput>
        <LabeledInput label="Publisher plugin">
          <select
            aria-label="Publisher plugin"
            value={pluginType}
            onChange={(e) => setPluginType(e.target.value)}
            className="px-2 py-2 text-sm"
            style={fieldStyle}
          >
            {(catalog?.publishers ?? []).map((plugin) => (
              <option key={plugin.name} value={plugin.name}>
                {plugin.name}
              </option>
            ))}
          </select>
        </LabeledInput>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          Enabled
        </label>
      </PluginFormGrid>
      <JsonField
        label="Adapter config"
        value={adapterConfig}
        onChange={setAdapterConfig}
      />
      <JsonField
        label="Column filter IDs"
        value={columnFilterIds}
        onChange={setColumnFilterIds}
      />
      <ActionRow>
        <button type="button" disabled={busy} onClick={() => void save(false)}>
          Update publisher
        </button>
        <button type="button" disabled={busy} onClick={() => void save(true)}>
          Create publisher
        </button>
        <button type="button" disabled={busy || !selectedId} onClick={() => void remove()}>
          Delete publisher
        </button>
      </ActionRow>
      {message && <StatusLine>{message}</StatusLine>}
    </Panel>
  );
}

function parseJsonObject(value: string, label: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(value || "{}") as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    // fall through
  }
  throw new Error(`${label} must be a JSON object.`);
}

function errorText(e: unknown): string {
  if (e instanceof Error) return e.message;
  return String(e);
}

function ConfigList({
  rows,
  selectedId,
  onSelect,
}: {
  rows: Array<{ id: string; name: string; pluginType: string; enabled: boolean }>;
  selectedId: string | null;
  onSelect: (id: string) => void;
}): React.JSX.Element {
  if (rows.length === 0) {
    return <p className="text-sm" style={{ color: "var(--tw-ink-muted)" }}>No configured rows.</p>;
  }
  return (
    <div className="grid gap-2">
      {rows.map((row) => (
        <button
          key={row.id}
          type="button"
          onClick={() => onSelect(row.id)}
          className="text-left px-3 py-2"
          style={{
            background:
              selectedId === row.id ? "var(--tw-accent-bg)" : "var(--tw-bg)",
            color: selectedId === row.id ? "var(--tw-accent-ink)" : "var(--tw-ink)",
            borderWidth: 1,
            borderStyle: "solid",
            borderColor:
              selectedId === row.id ? "var(--tw-accent)" : "var(--tw-border)",
            borderRadius: "var(--tw-radius)",
          }}
        >
          <span className="text-sm font-medium">{row.name}</span>
          <span className="ml-2 text-[11px]">{row.pluginType}</span>
          <span className="ml-2 text-[11px]">{row.enabled ? "enabled" : "disabled"}</span>
        </button>
      ))}
    </div>
  );
}

function PluginFormGrid({ children }: { children: React.ReactNode }): React.JSX.Element {
  return <div className="grid grid-cols-1 desktop:grid-cols-3 gap-3">{children}</div>;
}

function LabeledInput({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <label className="grid gap-1 text-xs" style={{ color: "var(--tw-ink-muted)" }}>
      {label}
      {children}
    </label>
  );
}

function JsonField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}): React.JSX.Element {
  return (
    <label className="grid gap-1 text-xs" style={{ color: "var(--tw-ink-muted)" }}>
      {label}
      <textarea
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={4}
        className="px-2 py-2 font-mono text-xs"
        style={fieldStyle}
      />
    </label>
  );
}

function ActionRow({ children }: { children: React.ReactNode }): React.JSX.Element {
  return (
    <div className="flex flex-wrap gap-2">
      {React.Children.map(children, (child) => {
        if (!React.isValidElement<{ style?: React.CSSProperties }>(child)) {
          return child;
        }
        return React.cloneElement(child, {
          style: { ...actionButtonStyle, ...child.props.style },
        });
      })}
    </div>
  );
}

function StatusLine({ children }: { children: React.ReactNode }): React.JSX.Element {
  return (
    <p className="text-xs px-3 py-2" style={{ background: "var(--tw-bg)", color: "var(--tw-ink-muted)" }}>
      {children}
    </p>
  );
}

const mono: React.CSSProperties = {
  fontFamily: "var(--tw-font-mono)",
  color: "var(--tw-accent)",
  fontSize: 13,
};

const fieldStyle: React.CSSProperties = {
  background: "var(--tw-bg)",
  color: "var(--tw-ink)",
  borderWidth: 1,
  borderStyle: "solid",
  borderColor: "var(--tw-border)",
  borderRadius: "var(--tw-radius)",
  width: "100%",
};

const actionButtonStyle: React.CSSProperties = {
  background: "var(--tw-accent-bg)",
  color: "var(--tw-accent-ink)",
  borderWidth: 1,
  borderStyle: "solid",
  borderColor: "var(--tw-accent)",
  borderRadius: "var(--tw-radius)",
  minHeight: 38,
  padding: "0 12px",
};

function Panel({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <section
      style={{
        background: "var(--tw-bg-panel)",
        borderWidth: 1,
        borderStyle: "solid",
        borderColor: "var(--tw-border)",
        borderRadius: "var(--tw-radius)",
        padding: 16,
      }}
      className="space-y-3"
    >
      <header className="space-y-0.5">
        <h2 className="tw-display text-base">{title}</h2>
        {hint && (
          <p className="text-[11px]" style={{ color: "var(--tw-ink-dim)" }}>
            {hint}
          </p>
        )}
      </header>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

function Row({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <div
      className="flex items-baseline justify-between gap-3 py-1"
      style={{
        borderBottomWidth: 1,
        borderBottomStyle: "solid",
        borderBottomColor: "var(--tw-border)",
      }}
    >
      <div className="min-w-0">
        <p
          className="tw-eyebrow text-[10px]"
          style={{ color: "var(--tw-ink-muted)" }}
        >
          {label}
        </p>
        {hint && (
          <p className="text-[11px]" style={{ color: "var(--tw-ink-dim)" }}>
            {hint}
          </p>
        )}
      </div>
      <div className="flex-shrink-0">{children}</div>
    </div>
  );
}
