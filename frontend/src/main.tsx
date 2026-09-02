import React from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { BRAND_NAME } from "./brand";
import "./fonts";
import "./main.css";

// Single source of truth for the document title — keeps the SPA tab label
// in sync with VITE_BRAND_NAME overrides instead of the static fallback
// in index.html.
document.title = BRAND_NAME;

// Cesium asset base — set before any @cesium/engine import that needs it.
// vite.config.ts injects CESIUM_BASE_URL as a compile-time constant.
declare const CESIUM_BASE_URL: string;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
(window as any).CESIUM_BASE_URL = CESIUM_BASE_URL;

const rootEl = document.getElementById("root");
if (!rootEl) throw new Error("missing #root element");

createRoot(rootEl).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
