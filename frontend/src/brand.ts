// Single source of truth for the user-visible product name in the SPA.
//
// The name isn't settled — we may rebrand before launch. Every visible
// "Target Workspace" string goes through this constant so a future rename
// is a one-line change (or one env var at build time).
//
// Override via Vite env at build:
//
//   VITE_BRAND_NAME="Acme Targeting" npm run build
//
// Backend has its own mirror (`src/target_workspace/brand.py`) — keep
// them in sync at deploy time.

const fromEnv =
  typeof import.meta !== "undefined" &&
  import.meta.env &&
  typeof import.meta.env.VITE_BRAND_NAME === "string"
    ? import.meta.env.VITE_BRAND_NAME.trim()
    : "";

export const BRAND_NAME: string = fromEnv || "Target Workspace";
