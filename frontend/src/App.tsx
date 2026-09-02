import React from "react";
/**
 * Target Workspace — single-page SPA.
 *
 * Flow:
 *   1. Bootstrap on mount — try GET /v1/auth/me. If 401, render Login.
 *   2. After login or successful me() — load /v1/boards. If none, render NewBoardForm.
 *   3. Once at least one board exists — render BoardView; if multiple boards
 *      were seeded (demo mode), the header surfaces a board picker.
 *
 * Per ADR 0011 (responsive): layout reflows on narrow widths via overflow-x-auto
 * on the kanban container. Touch-first interactions use full-width buttons and
 * the move-via-dropdown pattern (drag-drop is a post-MVP enhancement).
 */

import { useEffect, useState } from "react";

import { api, ApiError } from "./api";
import { AccountSecurityPage } from "./components/AccountSecurityPage";
import { AuditPage } from "./components/AuditPage";
import { BoardView } from "./components/BoardView";
import { DiagOverlay } from "./components/DiagOverlay";
import { Login } from "./components/Login";
import { NewBoardForm } from "./components/NewBoardForm";
import { SettingsPage } from "./components/SettingsPage";
import { TargetEditPage } from "./components/TargetEditPage";
import { matchRoute, useLocation } from "./router";
import type { Board, UserOut } from "./types";

type Status = "loading" | "anonymous" | "no-board" | "boarded" | "error";

const ROUTES = {
  edit: "/targets/:id/edit",
  settings: "/settings",
  account: "/account",
  audit: "/audit",
} as const;

export default function App(): React.JSX.Element {
  return (
    <>
      <AppInner />
      <DiagOverlay />
    </>
  );
}

function AppInner(): React.JSX.Element {
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<UserOut | null>(null);
  const [boards, setBoards] = useState<Board[]>([]);
  const [boardId, setBoardId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pathname = useLocation();
  const route = matchRoute(pathname, ROUTES);

  useEffect(() => {
    // Console-only build id so the deploy state is provable from
    // devtools without taking up screen real estate.
    // eslint-disable-next-line no-console
    console.info(
      `[target-workspace] build ${__BUILD_ID__} loaded at`,
      new Date().toISOString(),
    );
    void (async () => {
      try {
        const me = await api.me();
        setUser(me);
        await loadBoards();
      } catch {
        setStatus("anonymous");
      }
    })();
  }, []);

  async function loadBoards(): Promise<void> {
    try {
      const all = await api.listBoards();
      setBoards(all);
      if (all.length === 0) {
        setStatus("no-board");
      } else {
        setBoardId(all[0].id);
        setStatus("boarded");
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setUser(null);
        setBoards([]);
        setBoardId(null);
        setError(null);
        setStatus("anonymous");
        return;
      }
      setError(String(err));
      setStatus("error");
    }
  }

  if (status === "loading") {
    return (
      <main className="min-h-screen flex items-center justify-center bg-neutral-950 text-neutral-500">
        <p className="text-sm">Loading…</p>
      </main>
    );
  }

  if (status === "error") {
    return (
      <main className="min-h-screen flex items-center justify-center p-8 bg-neutral-950 text-red-400">
        <div className="max-w-md text-center space-y-2">
          <h1 className="text-lg font-semibold">Something went wrong</h1>
          <p className="text-sm font-mono">{error}</p>
        </div>
      </main>
    );
  }

  if (status === "anonymous" || !user) {
    return (
      <Login
        onLogin={async (u) => {
          setUser(u);
          await loadBoards();
        }}
      />
    );
  }

  if (status === "no-board") {
    return (
      <NewBoardForm
        onCreated={(b) => {
          setBoards([b]);
          setBoardId(b.id);
          setStatus("boarded");
        }}
      />
    );
  }

  // Route to the target editor or settings page when the URL matches.
  // Both are authenticated views that don't need an active board.
  if (route?.key === "edit" && route.params.id) {
    return <TargetEditPage user={user} targetId={route.params.id} />;
  }
  if (route?.key === "settings") {
    return <SettingsPage user={user} />;
  }
  if (route?.key === "account") {
    return <AccountSecurityPage user={user} />;
  }
  if (route?.key === "audit") {
    return <AuditPage user={user} />;
  }

  const currentBoard = boards.find((b) => b.id === boardId) ?? null;
  if (!currentBoard) {
    return <main className="p-8 text-neutral-500">No board.</main>;
  }

  return (
    <BoardView
      user={user}
      board={currentBoard}
      allBoards={boards}
      onSwitchBoard={(id) => setBoardId(id)}
      onBoardsChanged={async () => {
        const all = await api.listBoards();
        setBoards(all);
        if (all.length === 0) {
          setBoardId(null);
          setStatus("no-board");
        } else if (!all.some((b) => b.id === boardId)) {
          setBoardId(all[0].id);
        }
      }}
      onLogout={() => {
        setUser(null);
        setBoards([]);
        setBoardId(null);
        setStatus("anonymous");
      }}
    />
  );
}
