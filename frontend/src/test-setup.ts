// tw-2n2h: per-test setup for @testing-library/react.
// Registers extended matchers (toBeInTheDocument, toHaveAttribute, ...)
// and auto-cleans the DOM after each test.

import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});
