import React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Cartesian3,
  Color,
  HeadingPitchRange,
  ImageryLayer as CImageryLayer,
  Ion,
  Math as CMath,
  SceneMode,
  UrlTemplateImageryProvider,
  Viewer as CesiumViewer,
} from "cesium";
import {
  Entity,
  EllipseGraphics,
  LabelGraphics,
  PointGraphics,
  PolygonGraphics,
  PolylineGraphics,
  Viewer,
} from "resium";

import "cesium/Build/Cesium/Widgets/widgets.css";

import { api } from "../api";
import { trackStateOf, type TrackState } from "../track_state";
import type { Board, Target } from "../types";

const PRESENCE_REFRESH_MS = 10_000;

interface PresenceSnap {
  callsign: string;
  lat: number;
  lon: number;
  course: number | null;
  time: string;
}

// We don't use Cesium Ion's hosted assets, so kill the default token to
// suppress its splash and the failed default-world-imagery requests that
// otherwise log as 401s and slow first paint.
Ion.defaultAccessToken = "";

// Base imagery — OpenStreetMap tiles. NE-II ships with Cesium but only
// at 3 LOD levels (max units-per-pixel ~0.176°), which is essentially
// "one color per viewport" at tactical zoom (typically <0.5° wide). OSM
// goes to LOD 19, gives us streets, terrain, settlements — usable at
// AO scale. UrlTemplateImageryProvider is synchronous and sidesteps the
// Cesium 1.141 + Rolldown bug with TMS fromUrl.
//
// Future tw-45s: swap in a bundled higher-LOD source (e.g. NE 1:10m +
// SRTM-shaded reliefs at LOD 5-8) for offline / air-gapped deploys.
const OSM_BASE_LAYER = new CImageryLayer(
  new UrlTemplateImageryProvider({
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    maximumLevel: 19,
    credit: "© OpenStreetMap contributors",
  }),
  {},
);

interface Props {
  board: Board;
  targets: Target[];
  selectedTargetId: string | null;
  onSelectTarget: (t: Target) => void;
}

export function MapPane({
  board,
  targets,
  selectedTargetId,
  onSelectTarget,
}: Props): React.JSX.Element {
  const viewerRef = useRef<{ cesiumElement?: CesiumViewer }>(null);
  const [sceneMode, setSceneMode] = useState<"2D" | "3D">("3D");
  const [presence, setPresence] = useState<PresenceSnap[]>([]);

  // tw-43c2: poll the workspace PLI snapshot and project the assignees
  // of any visible target as moving glyphs. Polling cadence is 10s for
  // MVP; realtime presence.update WS subscription is a follow-up.
  useEffect(() => {
    const assignees = new Set<string>();
    for (const t of targets) {
      for (const cs of t.assigned_callsigns ?? []) assignees.add(cs);
    }
    if (assignees.size === 0) {
      setPresence([]);
      return undefined;
    }
    let cancelled = false;
    async function tick(): Promise<void> {
      try {
        const all = await api.listPresence();
        if (cancelled) return;
        setPresence(all.filter((p) => assignees.has(p.callsign)));
      } catch {
        // Presence is advisory; failure shouldn't blank the map.
      }
    }
    void tick();
    const handle = window.setInterval(() => void tick(), PRESENCE_REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, [targets]);

  // One-time Cesium scene setup after the Viewer mounts. Doing this
  // imperatively (rather than via Viewer props) sidesteps two issues:
  //
  //   1. Passing `baseLayer={layer}` as a Viewer prop sometimes loses
  //      against Cesium's default constructor-side imagery init,
  //      especially during HMR.
  //   2. Cesium 1.141 runs a "home view" camera animation on mount that
  //      overrides any flyTo we fire too early. We cancel that explicitly
  //      before our own camera positioning kicks in.
  useEffect(() => {
    const viewer = viewerRef.current?.cesiumElement;
    if (!viewer) return;
    // Don't removeAll() — keep Cesium's built-in NE-II fallback layer
    // (the one it provides when no Ion token is set). It's the same
    // texture set anyway. Just disable lighting + cancel home-fly.
    viewer.scene.globe.enableLighting = false;
    viewer.camera.cancelFlight();
  }, []);

  // Cesium needs an explicit resize() whenever its container changes
  // size — the canvas doesn't auto-track parent dimensions. Without
  // this, opening the mobile fullscreen overlay leaves the canvas at
  // its initial split-pane width and you only see the top-left chunk.
  useEffect(() => {
    const viewer = viewerRef.current?.cesiumElement;
    if (!viewer || typeof ResizeObserver === "undefined") return;
    const container = viewer.container as HTMLElement;
    if (!container) return;
    const ro = new ResizeObserver(() => {
      try {
        viewer.resize();
      } catch {
        // viewer may already be destroyed during teardown
      }
    });
    ro.observe(container);
    // Kick the first resize on mount so the freshly-mounted canvas
    // matches its container even before any layout change.
    viewer.resize();
    return () => ro.disconnect();
  }, []);

  // Fit camera to all targets whenever the visible set changes. Cesium
  // adds entity primitives asynchronously after React commits children,
  // so we poll the entity collection until it matches the target count
  // (bounded retry — bails after ~1.5s if entities never materialize).
  useEffect(() => {
    const viewer = viewerRef.current?.cesiumElement;
    if (!viewer || targets.length === 0) return;
    let cancelled = false;
    let attempts = 0;
    function tryFit(): void {
      if (cancelled || !viewer) return;
      attempts += 1;
      if (viewer.entities.values.length >= targets.length) {
        viewer.camera.cancelFlight();
        // Force a minimum range so a tight cluster (DF cone targets are
        // often within 1 km) doesn't drop the camera onto the surface
        // looking outward at the empty sky.
        void viewer.flyTo(viewer.entities, {
          duration: 0.8,
          offset: new HeadingPitchRange(
            0, // heading: north-up
            CMath.toRadians(-55), // pitch: tilted-down 55°
            50_000, // range: 50 km
          ),
        });
        return;
      }
      if (attempts < 20) {
        window.setTimeout(tryFit, 80);
      }
    }
    tryFit();
    return () => {
      cancelled = true;
    };
  }, [board.id, targets]);

  // Style colors are read from the active theme's CSS variables. We sample
  // them once per render so the map repaints when the user switches boards
  // (themes). getComputedStyle is cheap; the entity tree re-renders
  // anyway when these refs change.
  const palette = useMemo(() => {
    const root = document.documentElement;
    const cs = getComputedStyle(root);
    const accent = cs.getPropertyValue("--tw-accent").trim() || "#fbbf24";
    const approval =
      cs.getPropertyValue("--tw-approval").trim() || "#fbbf24";
    return {
      accent,
      approval,
      cAccent: Color.fromCssColorString(accent),
      cApproval: Color.fromCssColorString(approval),
      cSelected: Color.YELLOW,
    };
  // Re-read CSS vars whenever the active board (and therefore theme) changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [board.theme, board.id]);

  function entityColor(t: Target): Color {
    if (t.id === selectedTargetId) return palette.cSelected;
    // tw-49a: hazards always draw with the approval (warning) color,
    // regardless of cot_type affiliation. They're obstacles, not
    // contacts.
    if (t.custom_fields?.entity_kind === "hazard") {
      const state = trackStateOf(t.time).state;
      return palette.cApproval.withAlpha(alphaForState(state));
    }
    // Hostile-affiliation contacts (a-h-*) draw with the approval color
    // (warning red on most themes); other contacts use accent.
    const base = t.cot_type.startsWith("a-h-")
      ? palette.cApproval
      : palette.cAccent;
    const state = trackStateOf(t.time).state;
    return base.withAlpha(alphaForState(state));
  }

  function entityLabelText(t: Target): string {
    if (t.custom_fields?.entity_kind === "hazard") return `⚠ ${t.name}`;
    return t.name;
  }

  function targetEntity(t: Target): React.JSX.Element {
    const pos = Cartesian3.fromDegrees(t.lon, t.lat, t.hae ?? 0);
    const color = entityColor(t);
    const fill = color.withAlpha(0.35);
    // Entity label is just the callsign — age lives on the card. The
    // entity color/alpha already encodes freshness (via track_state),
    // so the textual age would be redundant noise at 50-entity scale.
    // tw-49a: hazards get a ⚠ prefix on the label.
    const labelText = entityLabelText(t);

    if (t.geometry_kind === "ellipse" && t.ellipse) {
      return (
        <Entity
          key={t.id}
          id={t.id}
          name={t.name}
          position={pos}
          onClick={() => onSelectTarget(t)}
        >
          <EllipseGraphics
            semiMajorAxis={t.ellipse.semi_major_m}
            semiMinorAxis={t.ellipse.semi_minor_m}
            rotation={CMath.toRadians(t.ellipse.bearing_deg)}
            material={fill}
            outline
            outlineColor={color}
            height={0}
          />
          <LabelGraphics
            text={labelText}
            font="12px JetBrainsMono, ui-monospace, monospace"
            fillColor={color}
            outlineWidth={2}
            pixelOffset={new Cartesian3(0, -16, 0) as unknown as never}
            showBackground
            backgroundColor={Color.fromCssColorString("#000000").withAlpha(0.6)}
          />
        </Entity>
      );
    }

    if (t.geometry_kind === "polygon" && t.polygon_vertices) {
      const flat = t.polygon_vertices.flatMap(([lat, lon]) => [lon, lat]);
      return (
        <Entity
          key={t.id}
          id={t.id}
          name={t.name}
          position={pos}
          onClick={() => onSelectTarget(t)}
        >
          <PolygonGraphics
            hierarchy={Cartesian3.fromDegreesArray(flat) as unknown as never}
            material={fill}
            outline
            outlineColor={color}
          />
          <PolylineGraphics
            positions={
              Cartesian3.fromDegreesArray([...flat, flat[0], flat[1]]) as unknown as never
            }
            material={color}
            width={2}
            clampToGround
          />
          <LabelGraphics
            text={labelText}
            font="12px JetBrainsMono, ui-monospace, monospace"
            fillColor={color}
            outlineWidth={2}
            pixelOffset={new Cartesian3(0, -16, 0) as unknown as never}
            showBackground
            backgroundColor={Color.fromCssColorString("#000000").withAlpha(0.6)}
          />
        </Entity>
      );
    }

    // Default: point. PointGraphics is cheap and renders well at all zooms.
    return (
      <Entity
        key={t.id}
        id={t.id}
        name={t.name}
        position={pos}
        onClick={() => onSelectTarget(t)}
      >
        <PointGraphics
          pixelSize={10}
          color={color}
          outlineColor={Color.WHITE}
          outlineWidth={2}
        />
        <LabelGraphics
          text={labelText}
          font="12px JetBrainsMono, ui-monospace, monospace"
          fillColor={color}
          outlineWidth={2}
          pixelOffset={new Cartesian3(0, -16, 0) as unknown as never}
          showBackground
          backgroundColor={Color.fromCssColorString("#000000").withAlpha(0.6)}
        />
      </Entity>
    );
  }

  return (
    <div
      className="relative w-full h-full"
      style={{ background: "var(--tw-bg)" }}
    >
      <Viewer
        ref={viewerRef}
        // Resium's `full` prop sizes the Cesium canvas to the BROWSER
        // WINDOW (not the parent), which breaks on mobile where the
        // layout viewport can differ from the visible viewport and on
        // anywhere the map is rendered inside a non-fullscreen pane.
        // Instead, size the wrapping div to 100% and let Cesium fill it.
        style={{ width: "100%", height: "100%", position: "absolute", inset: 0 }}
        baseLayer={OSM_BASE_LAYER}
        // Strip down the default UI; we provide our own theme-keyed chrome.
        animation={false}
        baseLayerPicker={false}
        fullscreenButton={false}
        geocoder={false}
        homeButton={false}
        infoBox={false}
        navigationHelpButton={false}
        sceneModePicker={false}
        selectionIndicator={false}
        timeline={false}
        navigationInstructionsInitiallyVisible={false}
        sceneMode={sceneMode === "2D" ? SceneMode.SCENE2D : SceneMode.SCENE3D}
      >
        {targets.map((t) => targetEntity(t))}
        {presence.map((p) => {
          // Dim if the last PLI fix is older than 30s; hide above 5min
          // by trusting the backend TTL (presence cache drops at 5min).
          const ageMs = Date.now() - new Date(p.time).getTime();
          const alpha = ageMs > 30_000 ? 0.4 : 0.9;
          const pos = Cartesian3.fromDegrees(p.lon, p.lat, 0);
          return (
            <Entity key={`pli-${p.callsign}`} id={`pli-${p.callsign}`} position={pos}>
              <PointGraphics
                pixelSize={6}
                color={Color.LIME.withAlpha(alpha)}
                outlineColor={Color.BLACK}
                outlineWidth={1}
              />
              <LabelGraphics
                text={p.callsign}
                font="10px JetBrainsMono, ui-monospace, monospace"
                fillColor={Color.LIME.withAlpha(alpha)}
                pixelOffset={new Cartesian3(0, -12, 0) as unknown as never}
                showBackground
                backgroundColor={Color.fromCssColorString("#000000").withAlpha(0.6)}
              />
            </Entity>
          );
        })}
      </Viewer>

      {/* Map chrome — zoom + recenter + 2D/3D, theme-keyed */}
      <div className="absolute top-3 right-3 flex flex-col gap-2 z-10">
        <ChromeGroup>
          {(["2D", "3D"] as const).map((mode) => (
            <ChromeButton
              key={mode}
              onClick={() => setSceneMode(mode)}
              ariaPressed={sceneMode === mode}
              active={sceneMode === mode}
              label={mode}
              tooltip={`Switch to ${mode}`}
            />
          ))}
        </ChromeGroup>
        <ChromeGroup>
          <ChromeButton
            label="+"
            tooltip="Zoom in"
            onClick={() => {
              const v = viewerRef.current?.cesiumElement;
              if (v) v.camera.zoomIn(v.camera.positionCartographic.height * 0.4);
            }}
          />
          <ChromeButton
            label="−"
            tooltip="Zoom out"
            onClick={() => {
              const v = viewerRef.current?.cesiumElement;
              if (v) v.camera.zoomOut(v.camera.positionCartographic.height * 0.6);
            }}
          />
        </ChromeGroup>
        <ChromeGroup>
          <ChromeButton
            label="⊙"
            tooltip="Recenter on all targets"
            onClick={() => {
              const v = viewerRef.current?.cesiumElement;
              if (!v || v.entities.values.length === 0) return;
              v.camera.cancelFlight();
              void v.flyTo(v.entities, {
                duration: 0.6,
                offset: new HeadingPitchRange(
                  0,
                  CMath.toRadians(-55),
                  50_000,
                ),
              });
            }}
          />
        </ChromeGroup>
      </div>
    </div>
  );
}

function alphaForState(state: TrackState): number {
  // Map renders coasting at reduced alpha (~"dashed" semantics — Cesium's
  // entity primitives don't expose a per-instance dash pattern at this
  // API level, so alpha + outline are the visible knob). Stale fades
  // further; lost is nearly invisible — the operator can re-show by
  // selecting it (selected => YELLOW override). This matches the chip
  // treatment on TargetCard.
  switch (state) {
    case "active":
      return 0.85;
    case "coasting":
      return 0.55;
    case "stale":
      return 0.35;
    case "lost":
      return 0.18;
  }
}

function ChromeGroup({
  children,
}: {
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <div
      className="flex gap-1"
      style={{
        background: "color-mix(in srgb, var(--tw-bg) 80%, transparent)",
        borderWidth: 1,
        borderStyle: "solid",
        borderColor: "var(--tw-border)",
        borderRadius: "var(--tw-radius)",
        padding: 4,
      }}
    >
      {children}
    </div>
  );
}

function ChromeButton({
  label,
  tooltip,
  onClick,
  active = false,
  ariaPressed,
}: {
  label: string;
  tooltip: string;
  onClick: () => void;
  active?: boolean;
  ariaPressed?: boolean;
}): React.JSX.Element {
  return (
    <button
      onClick={onClick}
      title={tooltip}
      aria-label={tooltip}
      aria-pressed={ariaPressed}
      className="tw-eyebrow text-[12px] px-3 leading-none"
      style={{
        background: active ? "var(--tw-accent-bg)" : "transparent",
        color: active ? "var(--tw-accent-ink)" : "var(--tw-ink-muted)",
        borderRadius: "calc(var(--tw-radius) * 0.6)",
        minHeight: 44,
        minWidth: 44,
      }}
    >
      {label}
    </button>
  );
}
