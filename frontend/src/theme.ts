// Theme palettes per ADR 0008 (malleability) + ADR 0011 (responsive).
//
// Each Board carries a `theme` field (a ThemeName); the BoardView applies
// the matching palette by setting CSS custom properties on
// document.documentElement. Components read those vars instead of hardcoded
// Tailwind colors, so a single switch repaints the whole app.
//
// Beyond color, each palette declares a full aesthetic identity: display
// font, body font, background pattern, border radius, and header treatment.
// The intent is that a single still frame is enough to identify which
// workspace you're looking at without reading the title.

import type { ThemeName } from "./types";

interface Palette {
  // background tiers
  bg: string;
  bgPanel: string;
  bgPanelHover: string;
  border: string;
  borderHover: string;
  // text tiers
  ink: string;
  inkMuted: string;
  inkDim: string;
  // accent (header label, focus rings, primary buttons)
  accent: string;
  accentBg: string;
  accentBgHover: string;
  accentInk: string;
  // approval / warning tint (used for `approval required` and gated controls)
  approval: string;
  // brand display label (top-left "TARGET WORKSPACE" line)
  brand: string;
  // top accent rail color (paints a thin line under the header)
  rail: string;

  // ── typography ──────────────────────────────────────────────────────
  // Display face — used for board name + eyebrow labels
  fontDisplay: string;
  // Body face — used for everything else
  fontBody: string;
  // Mono face — explicit override for fixed-width data (coordinates, ids)
  fontMono: string;
  // tracking and case of section headers ("FIND", "LEAD", "REPORT", etc.)
  headerTracking: string;
  headerTransform: "uppercase" | "none";
  headerWeight: string;
  // Card / panel corner radius. 0 = brutal/operational, 6 = friendly.
  radius: string;
  // Optional decorative background pattern (data-URI SVG). `none` for themes
  // that intentionally have no atmosphere.
  bgImage: string;
}

// Encode a small SVG as a data URI for use as background-image. Keeps the
// palette table self-contained — no extra asset round-trips.
function svgDataUri(svg: string): string {
  return `url("data:image/svg+xml;utf8,${encodeURIComponent(svg)}")`;
}

// Subtle blueprint dot grid — used by tactical to evoke a planning surface.
const TACTICAL_GRID = svgDataUri(
  `<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24'>
     <circle cx='1' cy='1' r='0.6' fill='%23c8ad7f' fill-opacity='0.06'/>
   </svg>`,
);

// Topographic contour ghost — used by SAR. Concentric arcs that suggest
// map relief; multiple ridges fill the canvas so the pattern reads on
// camera without becoming literal terrain.
const SAR_CONTOURS = svgDataUri(
  `<svg xmlns='http://www.w3.org/2000/svg' width='480' height='480' fill='none' stroke='%23ff6a3d' stroke-opacity='0.11' stroke-width='1'>
     <circle cx='90' cy='370' r='40' />
     <circle cx='90' cy='370' r='72' />
     <circle cx='90' cy='370' r='108' />
     <circle cx='90' cy='370' r='148' />
     <circle cx='90' cy='370' r='192' />
     <circle cx='380' cy='100' r='34' />
     <circle cx='380' cy='100' r='62' />
     <circle cx='380' cy='100' r='95' />
     <circle cx='380' cy='100' r='132' />
     <circle cx='380' cy='100' r='172' />
     <circle cx='240' cy='250' r='22' />
     <circle cx='240' cy='250' r='44' />
     <circle cx='240' cy='250' r='70' />
     <circle cx='240' cy='250' r='100' />
     <path d='M0 240 Q 120 200 240 250 T 480 230' stroke-opacity='0.08' />
     <path d='M0 200 Q 120 160 240 215 T 480 195' stroke-opacity='0.08' />
   </svg>`,
);

// ICS — orthogonal grid lines, evokes a status board.
const ICS_GRID = svgDataUri(
  `<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40'>
     <path d='M40 0 H0 V40' stroke='%236ea8d6' stroke-opacity='0.05' fill='none' stroke-width='0.5'/>
   </svg>`,
);

// Federal — fine cross-hatch that reads as government-document substrate.
const FEDERAL_GRID = svgDataUri(
  `<svg xmlns='http://www.w3.org/2000/svg' width='32' height='32'>
     <path d='M0 16 H32 M16 0 V32' stroke='%23d9b052' stroke-opacity='0.04' stroke-width='0.5'/>
   </svg>`,
);

const NEUTRAL = '"Geist Mono", ui-monospace, monospace';
const TACTICAL_MONO = '"JetBrains Mono", ui-monospace, monospace';
const PUBLIC_SANS = '"Public Sans", system-ui, -apple-system, sans-serif';
const BARLOW = '"Barlow Condensed", "Public Sans", system-ui, sans-serif';

const PALETTES: Record<ThemeName, Palette> = {
  // ── neutral — refined editorial baseline ─────────────────────────────
  // Pristine, no atmosphere. The "no aesthetic" theme — actually a
  // deliberate aesthetic. Hairline rules, monospace throughout, no texture.
  neutral: {
    bg: "#0a0a0a",
    bgPanel: "#141414",
    bgPanelHover: "#1f1f1f",
    border: "#262626",
    borderHover: "#3f3f46",
    ink: "#f5f5f5",
    inkMuted: "#a3a3a3",
    inkDim: "#525252",
    accent: "#fbbf24",
    accentBg: "#f59e0b",
    accentBgHover: "#fbbf24",
    accentInk: "#0a0a0a",
    approval: "#fbbf24",
    brand: "#fbbf24",
    rail: "#fbbf24",
    fontDisplay: NEUTRAL,
    fontBody: NEUTRAL,
    fontMono: NEUTRAL,
    headerTracking: "0.18em",
    headerTransform: "uppercase",
    headerWeight: "600",
    radius: "4px",
    bgImage: "none",
  },

  // ── tactical — real-tool ATAK/Toughbook look ─────────────────────────
  // Dark slate + olive + FDE. NO scanlines, NO phosphor green. Tight
  // technical mono, subtle blueprint dot grid. Reads as a planning surface
  // someone would actually use on a Toughbook.
  tactical: {
    bg: "#0a0c0a",
    bgPanel: "#12150f",
    bgPanelHover: "#1a1e15",
    border: "#2b3024",
    borderHover: "#3a4232",
    ink: "#e9eadc",
    inkMuted: "#8d937e",
    inkDim: "#5e6557",
    accent: "#c8ad7f", // FDE
    accentBg: "#4a5d23", // olive drab
    accentBgHover: "#637f30",
    accentInk: "#f0f0e0",
    approval: "#d39e3a", // amber
    brand: "#c8ad7f",
    rail: "#4a5d23",
    fontDisplay: TACTICAL_MONO,
    fontBody: TACTICAL_MONO,
    fontMono: TACTICAL_MONO,
    headerTracking: "0.22em",
    headerTransform: "uppercase",
    headerWeight: "700",
    radius: "0px",
    bgImage: TACTICAL_GRID,
  },

  // ── federal — govtech precision ──────────────────────────────────────
  // Public Sans throughout (literal US government typeface). Restrained
  // navy panels on near-black with buff cream ink and federal gold rail.
  // Fine cross-hatch substrate. NO stamps, NO manila. Reads as login.gov
  // / USDS admin tool, not Law & Order set dressing.
  federal: {
    bg: "#0b0d12",
    bgPanel: "#141822",
    bgPanelHover: "#1c2230",
    border: "#252b3a",
    borderHover: "#3a4258",
    ink: "#f0e8d3", // buff cream
    inkMuted: "#a89976",
    inkDim: "#6e6346",
    accent: "#d9b052", // federal gold
    accentBg: "#1d3a6e", // navy
    accentBgHover: "#2a4e8a",
    accentInk: "#f0e8d3",
    approval: "#b4332e", // stamp red (restrained, used only for approval gates)
    brand: "#d9b052",
    rail: "#d9b052",
    fontDisplay: PUBLIC_SANS,
    fontBody: PUBLIC_SANS,
    fontMono: '"Geist Mono", ui-monospace, monospace',
    headerTracking: "0.16em",
    headerTransform: "uppercase",
    headerWeight: "700",
    radius: "2px",
    bgImage: FEDERAL_GRID,
  },

  // ── sar — operational outdoor ─────────────────────────────────────────
  // Barlow Condensed for display (used sparingly). Hi-vis orange is an
  // accent for active signals — NOT splashed everywhere. Topographic
  // contours ghosted at low opacity in the background.
  sar: {
    bg: "#0f1219",
    bgPanel: "#1b1f28",
    bgPanelHover: "#262b37",
    border: "#363c4a",
    borderHover: "#4a5260",
    ink: "#f1f3f8",
    inkMuted: "#a8b0bd",
    inkDim: "#6e7787",
    accent: "#ff6a3d", // hi-vis safety orange — accent only
    accentBg: "#ff6a3d",
    accentBgHover: "#ff8a5e",
    accentInk: "#1a0d05",
    approval: "#fbd23d", // hi-vis caution yellow
    brand: "#ff6a3d",
    rail: "#ff6a3d",
    fontDisplay: BARLOW,
    fontBody: PUBLIC_SANS,
    fontMono: '"Geist Mono", ui-monospace, monospace',
    headerTracking: "0.14em",
    headerTransform: "uppercase",
    headerWeight: "600",
    radius: "3px",
    bgImage: SAR_CONTOURS,
  },

  // ── ics — government operations (EOC / NWS / FEMA) ───────────────────
  // Public Sans, operational blue with warning red. Grid-line background.
  // Authoritative, utilitarian, status-board feel.
  ics: {
    bg: "#0b1118",
    bgPanel: "#131c28",
    bgPanelHover: "#1c2939",
    border: "#28384a",
    borderHover: "#3b4f68",
    ink: "#e9f0f8",
    inkMuted: "#8a9eb3",
    inkDim: "#5a6e85",
    accent: "#6ea8d6", // operational sky blue
    accentBg: "#1e4d8c",
    accentBgHover: "#2a63b0",
    accentInk: "#f0f4fa",
    approval: "#dc2626", // warning red — explicit gate signal
    brand: "#6ea8d6",
    rail: "#1e4d8c",
    fontDisplay: PUBLIC_SANS,
    fontBody: PUBLIC_SANS,
    fontMono: '"Geist Mono", ui-monospace, monospace',
    headerTracking: "0.12em",
    headerTransform: "uppercase",
    headerWeight: "700",
    radius: "2px",
    bgImage: ICS_GRID,
  },
};

export function applyTheme(theme: ThemeName): void {
  const palette = PALETTES[theme] ?? PALETTES.neutral;
  const root = document.documentElement;
  for (const [key, value] of Object.entries(palette)) {
    const cssKey = "--tw-" + key.replace(/([A-Z])/g, "-$1").toLowerCase();
    root.style.setProperty(cssKey, value);
  }
  root.dataset.tw = theme;
}

export function paletteFor(theme: ThemeName): Palette {
  return PALETTES[theme] ?? PALETTES.neutral;
}
