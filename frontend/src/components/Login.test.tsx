/**
 * Login form tests (tw-p3a6).
 *
 * The sign-in form must NOT prefill any identity. Shipping a hardcoded
 * `admin@example.com` leaks a default account hint and trains users to
 * sign in as a shared admin — both are product no-nos.
 */

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { Login } from "./Login";

describe("Login", () => {
  it("does not prefill the identity field", () => {
    render(<Login onLogin={() => {}} />);
    const identifier = screen.getByLabelText(/login identifier/i) as HTMLInputElement;
    expect(identifier.value).toBe("");
  });

  it("starts with an empty password field", () => {
    render(<Login onLogin={() => {}} />);
    const password = screen.getByLabelText(/password/i) as HTMLInputElement;
    expect(password.value).toBe("");
  });

  it("accepts username-shaped identifiers instead of browser email validation", () => {
    render(<Login onLogin={() => {}} />);
    const identifier = screen.getByLabelText(/login identifier/i) as HTMLInputElement;
    expect(identifier.type).toBe("text");
    expect(identifier.autocomplete).toBe("username");
  });

  it("offers passwordless passkey sign-in", () => {
    render(<Login onLogin={() => {}} />);
    expect(screen.getByRole("button", { name: "Sign in with passkey" })).toBeVisible();
  });
});
