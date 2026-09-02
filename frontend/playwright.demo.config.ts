import { defineConfig } from "@playwright/test";

/**
 * Dedicated Playwright config for the demo walkthrough recording
 * (tw-4ty). Separate from the main e2e config so the recording
 * doesn't run on every CI invocation and so the video output goes
 * exactly where the demo deliverables live (../docs/demo/raw/).
 *
 * Output:
 *   ../docs/demo/raw/demo-walkthrough.webm   (Playwright-recorded)
 *
 * A post-recording ffmpeg pass + caption authoring step produces:
 *   ../docs/demo/demo-walkthrough.mp4
 *   ../docs/demo/demo-walkthrough.webm  (re-encoded if needed)
 *   ../docs/demo/demo-walkthrough.vtt   (closed captions)
 *
 * Drive the whole pipeline through scripts/record-demo.sh from the
 * frontend/ directory.
 */
export default defineConfig({
  testDir: "./tests/demo",
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: "list",
  timeout: 120_000, // 2 min — bound the recorder so failures fail fast.
  expect: { timeout: 5_000 },
  outputDir: "../docs/demo/raw",
  use: {
    baseURL: "http://127.0.0.1:8000",
    trace: "off",
    timezoneId: "America/New_York",
    video: { mode: "on", size: { width: 1920, height: 1080 } },
  },
  projects: [
    {
      name: "desktop-1080p",
      use: { viewport: { width: 1920, height: 1080 } },
    },
  ],
});
