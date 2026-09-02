import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";
import cesium from "vite-plugin-cesium";
import { compression } from "vite-plugin-compression2";
import path from "node:path";

// vite-plugin-cesium handles:
//   • injecting `CESIUM_BASE_URL` as a compile-time define
//   • serving Cesium static assets (Workers/, Assets/, ThirdParty/,
//     Widgets/) from `/cesium/` in dev via middleware
//   • copying those same assets into `dist/cesium/` for production build
// rebuildCesium: true bundles cesium into our app chunk instead of
// externalizing it as a runtime global (which is what the default mode
// expects, requires a separate <script src="…/Cesium.js"> include).
//
// Pre-compressed brotli + gzip variants are written next to every JS,
// CSS, HTML, SVG, and SkyBox/Assets/Workers file. The FastAPI static
// handler serves them based on Accept-Encoding so the runtime gzip
// middleware doesn't need to recompress every request. At max levels
// (br=11, gzip=9) the Cesium chunk drops from ~1.3 MB to ~900 KB.
// Inject a build-time timestamp string so the SPA can render which
// bundle the browser is actually loading. Useful when "did the fix
// deploy?" needs a definitive answer in a deployed environment.
const BUILD_ID = new Date().toISOString().replace(/[:.]/g, "-");

export default defineConfig({
  define: {
    __BUILD_ID__: JSON.stringify(BUILD_ID),
  },
  plugins: [
    tailwindcss(),
    cesium({ rebuildCesium: true }),
    compression({
      algorithms: ["brotliCompress", "gzip"],
      threshold: 1024,
      exclude: [/\.(br|gz)$/],
    }),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    host: "127.0.0.1",
    proxy: {
      // Backend API during dev; production serves frontend behind FastAPI.
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/healthz": "http://127.0.0.1:8000",
      "/readyz": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
    // No prod sourcemaps: generating the ~18MB map for the Cesium bundle is
    // the peak-memory step of the build (~812MB vs ~709MB without), which
    // OOM-kills the build on the memory-constrained CI runner. Drop it to keep
    // the build under budget. Re-enable locally if you need to debug a bundle.
    sourcemap: false,
    target: "es2022",
  },
});
