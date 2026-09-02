/**
 * Sample component test under @testing-library/react (tw-2n2h).
 *
 * Exercises AgeCounter — a small, dependency-light component — to
 * prove the testing harness is wired. Heavier components adopt the
 * same pattern in v1.x.
 */

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { AgeCounter } from "./AgeCounter";

describe("AgeCounter", () => {
  it("renders an age string for a recent observation", () => {
    const tenSecondsAgo = new Date(Date.now() - 10_000).toISOString();
    render(<AgeCounter observedAtIso={tenSecondsAgo} />);
    // The text content should mention seconds (small unit).
    const el = screen.getByTitle(/observed/i);
    expect(el).toBeInTheDocument();
    expect(el.textContent || "").toMatch(/\d/);
  });

  it("respects the md size variant", () => {
    const ts = new Date().toISOString();
    const { container } = render(<AgeCounter observedAtIso={ts} size="md" />);
    const span = container.querySelector("span");
    expect(span).toBeTruthy();
    // The md variant sets font-size to 13.
    expect((span as HTMLElement).style.fontSize).toBe("13px");
  });
});
