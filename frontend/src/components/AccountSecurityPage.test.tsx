import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AccountSecurityPage } from "./AccountSecurityPage";
import { ApiError, api } from "../api";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    api: {
      changePassword: vi.fn(),
      listPasskeys: vi.fn().mockResolvedValue([]),
      listApiTokens: vi.fn().mockResolvedValue([]),
      createApiToken: vi.fn(),
      revokeApiToken: vi.fn(),
      passkeyRegistrationOptions: vi.fn(),
      enrollTotp: vi.fn(),
      revokeAllSessions: vi.fn(),
    },
  };
});

const user = {
  id: "user-1",
  email: "operator@example.com",
  display_name: "Operator One",
  role: "operator",
  must_change_password: false,
  mfa_enabled: false,
};

describe("AccountSecurityPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the self-service auth sections without prefilled credentials", () => {
    render(<AccountSecurityPage user={user} />);

    expect(screen.getByRole("heading", { name: "Account & Security" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Profile" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Passkeys" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Password" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Two-factor authentication" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Active sessions" })).toBeVisible();

    expect(screen.getByLabelText("Current password")).toHaveValue("");
    expect(screen.getByLabelText("New password")).toHaveValue("");
  });

  it("shows clear empty passkey state instead of registered none", async () => {
    render(<AccountSecurityPage user={user} />);

    expect(
      await screen.findByText("No passkeys registered."),
    ).toBeVisible();
    expect(screen.queryByText("Registered")).not.toBeInTheDocument();
    expect(screen.queryByText("None")).not.toBeInTheDocument();
  });

  it("surfaces passkey registration API failures as actionable text", async () => {
    Object.defineProperty(window, "PublicKeyCredential", {
      configurable: true,
      value: vi.fn(),
    });
    Object.defineProperty(navigator, "credentials", {
      configurable: true,
      value: { create: vi.fn() },
    });
    vi.mocked(api.passkeyRegistrationOptions).mockRejectedValueOnce(
      new ApiError(400, { detail: "invalid passkey" }),
    );

    render(<AccountSecurityPage user={user} />);
    await userEvent.click(screen.getByRole("button", { name: "Register passkey" }));

    await waitFor(() =>
      expect(screen.getByText("Passkey registration failed: invalid passkey")).toBeVisible(),
    );
  });

  it("shows API token scopes and allows revocation", async () => {
    vi.mocked(api.listApiTokens).mockResolvedValueOnce([
      {
        id: "token-1",
        name: "readonly bot",
        role: "operator",
        scopes: ["boards:read", "targets:read"],
        preview: "abcdef12",
        expires_at: null,
        created_at: "2026-06-04T19:00:00Z",
        last_used_at: null,
        revoked_at: null,
      },
    ]);

    render(<AccountSecurityPage user={user} />);

    expect(await screen.findByRole("heading", { name: "API tokens" })).toBeVisible();
    expect(screen.getByText("readonly bot")).toBeVisible();
    expect(screen.getAllByText("boards:read").length).toBeGreaterThan(0);
    expect(screen.getAllByText("targets:read").length).toBeGreaterThan(0);

    await userEvent.click(screen.getByRole("button", { name: "Revoke readonly bot" }));

    expect(api.revokeApiToken).toHaveBeenCalledWith("token-1");
    await waitFor(() => expect(api.listApiTokens).toHaveBeenCalledTimes(2));
  });

  it("creates a scoped API token and shows the plaintext once", async () => {
    vi.mocked(api.createApiToken).mockResolvedValueOnce({
      id: "token-2",
      name: "field bot",
      token: "tw_live_plaintext",
      role: "operator",
      scopes: ["boards:read", "targets:read"],
      preview: "tw_live_",
      expires_at: null,
    });

    render(<AccountSecurityPage user={user} />);

    await userEvent.type(await screen.findByLabelText("Token name"), "field bot");
    await userEvent.click(screen.getByLabelText("boards:read"));
    await userEvent.click(screen.getByLabelText("targets:read"));
    await userEvent.click(screen.getByRole("button", { name: "Create API token" }));

    expect(api.createApiToken).toHaveBeenCalledWith("field bot", [
      "boards:read",
      "targets:read",
    ]);
    expect(await screen.findByText("tw_live_plaintext")).toBeVisible();
  });
});
