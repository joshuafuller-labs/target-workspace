import type { Config } from "tailwindcss";

// Tailwind 4 reads most config from CSS via @theme directives in src/main.css.
// This file remains for tooling that still expects a JS/TS config entry.
const config: Config = {
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};

export default config;
