import { defineConfig } from "vitest/config";

/**
 * Vitest config — unit-tests only. The e2e .spec.ts files under
 * tests/e2e/ are owned by Playwright; excluding them here keeps
 * `npm test` fast and prevents vitest from trying to load
 * @playwright/test as a unit module.
 */
export default defineConfig({
  test: {
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    exclude: ["tests/e2e/**", "node_modules/**", "dist/**"],
    // tw-2n2h: jsdom for component tests under @testing-library/react.
    environment: "jsdom",
    setupFiles: ["src/test-setup.ts"],
  },
});
