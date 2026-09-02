import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { BoardView } from "./BoardView";
import type { Board, UserOut } from "../types";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    api: {
      listTargets: vi.fn().mockResolvedValue([]),
      listAudit: vi.fn().mockResolvedValue([]),
      logout: vi.fn().mockResolvedValue({ status: "ok" }),
    },
  };
});

vi.mock("../realtime", () => ({
  connectRealtime: vi.fn(() => () => undefined),
}));

const board: Board = {
  id: "board-1",
  name: "Ops",
  transitions: "unrestricted",
  theme: "neutral",
  columns: [{ id: "col-1", name: "Find", order: 0, wip_limit: null, color: null, requires_approval: false }],
};

const user: UserOut = {
  id: "user-1",
  email: "operator@example.com",
  display_name: "Operator One",
  role: "operator",
  must_change_password: false,
  mfa_enabled: false,
};

describe("BoardView user menu", () => {
  it("links to Account & Security from the header menu", async () => {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockReturnValue({ matches: false }),
    });

    render(
      <BoardView
        user={user}
        board={board}
        allBoards={[board]}
        onSwitchBoard={vi.fn()}
        onBoardsChanged={vi.fn()}
        onLogout={vi.fn()}
      />,
    );

    const menuButton = screen.getByRole("button", { name: "Open menu" });
    expect(menuButton).toHaveTextContent("Menu");
    expect(menuButton).not.toHaveTextContent("OO");

    await userEvent.click(menuButton);

    await waitFor(() =>
      expect(screen.getByRole("link", { name: "Account & Security" })).toHaveAttribute(
        "href",
        "/settings",
      ),
    );
  });
});
