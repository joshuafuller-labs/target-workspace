import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { ApiError, api } from "./api";

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return {
    ...actual,
    api: {
      me: vi.fn(),
      listBoards: vi.fn(),
      listPasskeys: vi.fn().mockResolvedValue([]),
      listApiTokens: vi.fn().mockResolvedValue([]),
      createApiToken: vi.fn(),
      revokeApiToken: vi.fn(),
    },
  };
});

describe("App auth bootstrap", () => {
  beforeEach(() => {
    vi.stubGlobal("__BUILD_ID__", "test");
    window.history.replaceState(null, "", "/");
    vi.mocked(api.me).mockReset();
    vi.mocked(api.listBoards).mockReset();
    vi.mocked(api.listPasskeys).mockReset();
    vi.mocked(api.listPasskeys).mockResolvedValue([]);
    vi.mocked(api.listApiTokens).mockReset();
    vi.mocked(api.listApiTokens).mockResolvedValue([]);
    vi.mocked(api.createApiToken).mockReset();
    vi.mocked(api.revokeApiToken).mockReset();
  });

  it("shows login instead of the generic error screen when the session check returns 401", async () => {
    vi.mocked(api.me).mockRejectedValue(new ApiError(401, { detail: "user not found" }));

    render(<App />);

    await waitFor(() => expect(screen.getByRole("heading", { name: "Sign in" })).toBeVisible());
    expect(screen.queryByText("Something went wrong")).not.toBeInTheDocument();
  });

  it("renders the account security route for an authenticated user", async () => {
    window.history.replaceState(null, "", "/account");
    vi.mocked(api.me).mockResolvedValue({
      id: "user-1",
      email: "operator@example.com",
      display_name: "Operator One",
      role: "operator",
      must_change_password: false,
      mfa_enabled: false,
    });
    vi.mocked(api.listBoards).mockResolvedValue([
      {
        id: "board-1",
        name: "Ops",
        transitions: "unrestricted",
        theme: "neutral",
        columns: [],
      },
    ]);

    render(<App />);

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Account & Security" })).toBeVisible(),
    );
  });
});
