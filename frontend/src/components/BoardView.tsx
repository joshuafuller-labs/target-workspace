import React from "react";
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import {
  planCrossColumnDropOnCard,
  planSameColumnReorder,
} from "../reorder";

import { api, ApiError } from "../api";
import { BRAND_NAME } from "../brand";
import { EMPTY_FILTER, matchesTarget, parseQuery, type FilterSpec } from "../filter";
import { connectRealtime } from "../realtime";
import { applyTheme } from "../theme";
import type { AuditEventOut, Board, Target, UserOut } from "../types";
import { ApprovalPrompt } from "./ApprovalPrompt";
import { BoardEditForm } from "./BoardEditForm";
import { HeaderQuickLinks } from "./HeaderQuickLinks";
import { HintCard } from "./HintCard";
import { NewBoardForm } from "./NewBoardForm";
import { NewTargetForm } from "./NewTargetForm";
import { TargetCard } from "./TargetCard";
import { TargetDetail } from "./TargetDetail";

// Lazy-load MapPane so Cesium (~3 MB of the bundle) doesn't ship with
// the login screen or the kanban. The chunk only downloads when the
// user actually opens the map.
const MapPane = lazy(() =>
  import("./MapPane").then((m) => ({ default: m.MapPane })),
);

interface Props {
  user: UserOut;
  board: Board;
  allBoards: Board[];
  onSwitchBoard: (id: string) => void;
  /** Reload the boards list (after create / edit / delete). Parent
   *  picks the next board to show when the active one disappears. */
  onBoardsChanged: () => Promise<void> | void;
  onLogout: () => void;
}

interface ColumnState {
  columnId: string;
  targets: Target[];
}

// Holds the in-flight drag operation when the destination is approval-gated:
// the optimistic move has already been applied to local state, but the
// server call has been deferred until the user supplies an approving role.
interface PendingApproval {
  target: Target;
  fromColumnId: string;
  toColumn: Board["columns"][number];
}

export function BoardView({
  user,
  board,
  allBoards,
  onSwitchBoard,
  onBoardsChanged,
  onLogout,
}: Props): React.JSX.Element {
  const [byColumn, setByColumn] = useState<ColumnState[]>([]);
  const [showNewTarget, setShowNewTarget] = useState(false);
  const [selectedTarget, setSelectedTarget] = useState<Target | null>(null);
  const [audit, setAudit] = useState<AuditEventOut[]>([]);
  const [showAudit, setShowAudit] = useState(false);
  const [liveStatus, setLiveStatus] = useState<"connecting" | "open" | "closed">(
    "connecting",
  );
  const [showMap, setShowMap] = useState(() => {
    // Default: open on REAL desktop (width AND height both clear the
    // threshold). On phone-landscape (844x390) the width clears 768 but
    // height (390) doesn't clear 600, so we treat that as mobile and
    // start with the map closed — otherwise the fullscreen overlay
    // covers the kanban on first paint. Same media query as the
    // `desktop:` custom variant in main.css.
    if (typeof window === "undefined") return true;
    return window.matchMedia(
      "(min-width: 768px) and (min-height: 600px)",
    ).matches;
  });
  const [activeTarget, setActiveTarget] = useState<Target | null>(null);
  const [pending, setPending] = useState<PendingApproval | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [showBoardEdit, setShowBoardEdit] = useState(false);
  const [showNewBoard, setShowNewBoard] = useState(false);
  // Set of target IDs that should pulse on arrival. Populated when a
  // target.created / target.updated event lands; entries auto-clear
  // after 5s via setTimeout. The pulse is an attention-grabber for new
  // observations, distinct from the static freshness signal on the
  // age counter.
  const [flashIds, setFlashIds] = useState<Set<string>>(() => new Set());
  // Read initial filter from the URL so a shared link reproduces the
  // exact filtered view. Writes back via history.replaceState on every
  // change — no router round-trip needed.
  const [filter, setFilter] = useState<FilterSpec>(() => {
    if (typeof window === "undefined") return EMPTY_FILTER;
    const q = new URLSearchParams(window.location.search).get("q");
    return q ? parseQuery(q) : EMPTY_FILTER;
  });

  // Keep the column-by-column snapshot in a ref so DnD handlers can compute
  // optimistic state without re-running on every render.
  const byColumnRef = useRef<ColumnState[]>([]);
  useEffect(() => {
    byColumnRef.current = byColumn;
  }, [byColumn]);

  useEffect(() => {
    applyTheme(board.theme ?? "neutral");
  }, [board.theme]);

  // Mirror the filter into the URL query string. URL is the source of
  // truth for sharing; this keeps it in sync without rerouting.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    if (filter.raw.trim()) url.searchParams.set("q", filter.raw);
    else url.searchParams.delete("q");
    window.history.replaceState(null, "", url.toString());
  }, [filter.raw]);

  async function refresh(): Promise<void> {
    const next: ColumnState[] = [];
    for (const c of board.columns) {
      next.push({ columnId: c.id, targets: await api.listTargets(board.id, c.id) });
    }
    setByColumn(next);
    setAudit(await api.listAudit());
  }

  useEffect(() => {
    void refresh();
  }, [board.id]);

  useEffect(() => {
    const close = connectRealtime({
      boardId: board.id,
      onStatusChange: setLiveStatus,
      onEvent: (e) => {
        if (
          e.type === "target.created" ||
          e.type === "target.moved" ||
          e.type === "target.updated" ||
          e.type === "target.reordered"
        ) {
          void refresh();
          // Flash the affected card for ~5s so the operator's eye
          // catches the change. Uses functional setState to avoid
          // stale-closure issues.
          const id = e.target_id;
          if (id) {
            setFlashIds((prev) => {
              const next = new Set(prev);
              next.add(id);
              return next;
            });
            window.setTimeout(() => {
              setFlashIds((prev) => {
                if (!prev.has(id)) return prev;
                const next = new Set(prev);
                next.delete(id);
                return next;
              });
            }, 5_000);
          }
        }
      },
    });
    return close;
  }, [board.id]);

  async function handleLogout(): Promise<void> {
    try {
      await api.logout();
    } finally {
      onLogout();
    }
  }

  // ── DnD plumbing ────────────────────────────────────────────────────
  //
  // PointerSensor handles mouse + touch (touchAction: none on the card).
  // distance: 6 keeps a quick click from registering as a drag, so
  // click-to-open still works alongside drag-to-move.
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor),
  );

  function findColumnOfTarget(targetId: string): string | null {
    for (const col of byColumnRef.current) {
      if (col.targets.some((t) => t.id === targetId)) return col.columnId;
    }
    return null;
  }

  function applyOptimisticMove(
    targetId: string,
    fromColumnId: string,
    toColumnId: string,
  ): Target | null {
    let moved: Target | null = null;
    setByColumn((prev) => {
      const next = prev.map((c) => ({ ...c, targets: [...c.targets] }));
      const from = next.find((c) => c.columnId === fromColumnId);
      const to = next.find((c) => c.columnId === toColumnId);
      if (!from || !to) return prev;
      const idx = from.targets.findIndex((t) => t.id === targetId);
      if (idx < 0) return prev;
      moved = from.targets.splice(idx, 1)[0];
      to.targets.unshift(moved);
      return next;
    });
    return moved;
  }

  function onDragStart(e: DragStartEvent): void {
    const t = e.active.data.current?.target as Target | undefined;
    if (t) setActiveTarget(t);
  }

  async function performMove(
    target: Target,
    toColumnId: string,
    fromColumnId: string,
    opts?: { approvingRole?: string; justification?: string },
  ): Promise<void> {
    try {
      await api.moveTarget(target.id, toColumnId, {
        approving_role: opts?.approvingRole,
        justification: opts?.justification,
      });
      // Realtime WS event will trigger refresh on every connected client;
      // for the moving client we also refresh locally so the version bumps.
      void refresh();
    } catch (err) {
      // Roll back the optimistic placement and resync from server truth.
      console.warn("Move rejected:", err);
      if (err instanceof ApiError) {
        const detail =
          typeof err.detail === "object" && err.detail && "detail" in err.detail
            ? (err.detail as { detail?: string }).detail
            : err.message;
        // Best-effort user feedback. A toast component is post-MVP.
        window.alert(`Move rejected: ${detail ?? err.message}`);
      }
      // Putting the card back is just a server-truth refresh.
      void refresh();
      // Touch fromColumnId so the unused-var lint stays happy when the
      // refresh path runs.
      void fromColumnId;
    }
  }

  function onDragEnd(e: DragEndEvent): void {
    setActiveTarget(null);
    const { active, over } = e;
    if (!over) return;
    const target = active.data.current?.target as Target | undefined;
    if (!target) return;
    const fromColumnId = findColumnOfTarget(target.id);
    if (!fromColumnId) return;

    const overType = over.data.current?.type as string | undefined;

    // Case A: dropped on another card. Drop AT the slot the over-card
    // currently occupies (the over-card slides out of the way). Use
    // arrayMove for direction-aware semantics: drag-down puts active
    // AFTER the over-card; drag-up puts active BEFORE it. after_id
    // for the server is then "the card immediately preceding active
    // in the post-move array."
    if (overType === "target") {
      const overTarget = over.data.current?.target as Target;
      if (overTarget.id === target.id) return;
      const overColumnId = findColumnOfTarget(overTarget.id);
      if (!overColumnId) return;
      const destCol = byColumnRef.current.find(
        (c) => c.columnId === overColumnId,
      );
      if (!destCol) return;
      const overIdx = destCol.targets.findIndex((t) => t.id === overTarget.id);
      if (overIdx < 0) return;

      if (overColumnId === fromColumnId) {
        const plan = planSameColumnReorder(
          destCol.targets,
          target.id,
          overTarget.id,
        );
        if (!plan) return;
        applyOptimisticReorderAbsolute(
          target.id,
          overColumnId,
          plan.nextOrder,
        );
        void performReorder(target, overColumnId, plan.afterId, fromColumnId);
        return;
      }
      // Cross-column drop onto a card.
      const toColumn = board.columns.find((c) => c.id === overColumnId);
      if (!toColumn) return;
      const plan = planCrossColumnDropOnCard(
        destCol.targets,
        target,
        overTarget.id,
      );
      if (!plan) return;
      applyOptimisticMove(target.id, fromColumnId, overColumnId);
      if (toColumn.requires_approval) {
        setPending({ target, fromColumnId, toColumn });
        return;
      }
      void (async () => {
        await performMove(target, overColumnId, fromColumnId);
        try {
          await api.reorderTarget(target.id, overColumnId, plan.afterId);
          void refresh();
        } catch {
          /* primary move succeeded */
        }
      })();
      return;
    }

    // Case B: dropped on a column droppable (empty space). This is
    // the existing cross-column move path.
    const toColumnId = over.data.current?.columnId as string | undefined;
    if (!toColumnId || fromColumnId === toColumnId) return;
    const toColumn = board.columns.find((c) => c.id === toColumnId);
    if (!toColumn) return;
    applyOptimisticMove(target.id, fromColumnId, toColumnId);
    if (toColumn.requires_approval) {
      setPending({ target, fromColumnId, toColumn });
      return;
    }
    void performMove(target, toColumnId, fromColumnId);
  }

  function applyOptimisticReorderAbsolute(
    _targetId: string,
    columnId: string,
    nextOrder: Target[],
  ): void {
    setByColumn((prev) =>
      prev.map((c) => (c.columnId === columnId ? { ...c, targets: nextOrder } : c)),
    );
  }

  async function performReorder(
    target: Target,
    columnId: string,
    afterId: string | null,
    _fromColumnId: string,
  ): Promise<void> {
    try {
      await api.reorderTarget(target.id, columnId, afterId);
      // Realtime WS event re-syncs everyone; local refresh keeps the
      // server-authoritative position in sync after the optimistic
      // splice.
      void refresh();
    } catch (err) {
      console.warn("Reorder rejected:", err);
      void refresh();
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      <header
        className="tw-rail relative px-3 desktop:px-6 py-3 border-b"
        style={{ borderColor: "var(--tw-border)" }}
      >
        {/* Row 1: brand + board status (always visible) + menu toggle (mobile) */}
        <div className="flex items-center gap-3 desktop:gap-5 desktop:flex-wrap">
          <div className="leading-tight min-w-0 flex-1 desktop:flex-initial">
            <p
              className="tw-eyebrow text-[10px] truncate"
              style={{ color: "var(--tw-brand)" }}
            >
              {BRAND_NAME}
            </p>
            <h1 className="tw-display text-lg desktop:text-xl mt-0.5 truncate">
              {board.name}
            </h1>
          </div>
          {allBoards.length > 1 && (
            <select
              value={board.id}
              onChange={(e) => onSwitchBoard(e.target.value)}
              className="hidden desktop:block px-3 py-1.5 text-sm focus:outline-none"
              style={{
                background: "var(--tw-bg-panel)",
                borderWidth: 1,
                borderStyle: "solid",
                borderColor: "var(--tw-border)",
                borderRadius: "var(--tw-radius)",
                color: "var(--tw-ink)",
                fontFamily: "var(--tw-font-body)",
                minHeight: 44,
              }}
              aria-label="Switch board"
            >
              {allBoards.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          )}
          {isCommanderOrAdmin(user.role) && (
            <div className="hidden desktop:flex items-center gap-2">
              <button
                onClick={() => setShowBoardEdit(true)}
                className="tw-eyebrow text-[11px] px-3"
                style={{
                  background: "var(--tw-bg-panel)",
                  borderWidth: 1,
                  borderStyle: "solid",
                  borderColor: "var(--tw-border)",
                  borderRadius: "var(--tw-radius)",
                  color: "var(--tw-ink-muted)",
                  minHeight: 44,
                }}
                title="Rename / re-theme / delete this board"
              >
                Edit board
              </button>
              <button
                onClick={() => setShowNewBoard(true)}
                className="tw-eyebrow text-[11px] px-3"
                style={{
                  background: "var(--tw-bg-panel)",
                  borderWidth: 1,
                  borderStyle: "solid",
                  borderColor: "var(--tw-border)",
                  borderRadius: "var(--tw-radius)",
                  color: "var(--tw-ink-muted)",
                  minHeight: 44,
                }}
                title="Create a new board"
              >
                + Board
              </button>
            </div>
          )}
          {/* Desktop: filter inline. Mobile: filter goes to row 2. */}
          <div className="hidden desktop:block flex-1 min-w-[200px] max-w-md">
            <FilterInput
              value={filter.raw}
              onChange={(raw) => setFilter(parseQuery(raw))}
            />
          </div>
          <div className="hidden desktop:flex items-center gap-5">
            <HeaderQuickLinks />
            <button
              onClick={() => setShowMap((v) => !v)}
              className="px-3 py-1.5 text-sm"
              style={{
                background: showMap ? "var(--tw-bg-panel)" : "transparent",
                borderWidth: 1,
                borderStyle: "solid",
                borderColor: "var(--tw-border)",
                borderRadius: "var(--tw-radius)",
                color: "var(--tw-ink)",
                fontFamily: "var(--tw-font-body)",
                minHeight: 44,
              }}
              aria-pressed={showMap}
            >
              {showMap ? "Hide map" : "Show map"}
            </button>
            <button
              onClick={() => setShowAudit((v) => !v)}
              className="px-3 py-1.5 text-sm"
              style={{
                background: "var(--tw-bg-panel)",
                borderWidth: 1,
                borderStyle: "solid",
                borderColor: "var(--tw-border)",
                borderRadius: "var(--tw-radius)",
                color: "var(--tw-ink)",
                fontFamily: "var(--tw-font-body)",
                minHeight: 44,
              }}
            >
              {showAudit ? "Hide audit" : "Audit log"}
            </button>
            <button
              onClick={() => setShowNewTarget(true)}
              className="tw-eyebrow px-4 py-1.5 text-[11px]"
              style={{
                background: "var(--tw-accent-bg)",
                color: "var(--tw-accent-ink)",
                borderRadius: "var(--tw-radius)",
                minHeight: 44,
              }}
            >
              + New Target
            </button>
          </div>
          {/* Menu trigger — same control on desktop and mobile so Settings and
              account actions are reachable regardless of screen size. */}
          <div className="flex items-center gap-2">
            <LiveIndicator status={liveStatus} compact />
            <button
              onClick={() => setMobileMenuOpen(true)}
              aria-label="Open menu"
              className="tw-eyebrow text-[12px] px-3 inline-flex items-center gap-2"
              style={{
                background: "var(--tw-bg-panel)",
                borderWidth: 1,
                borderStyle: "solid",
                borderColor: "var(--tw-border)",
                borderRadius: "var(--tw-radius)",
                color: "var(--tw-ink)",
                minHeight: 44,
                minWidth: 44,
              }}
            >
              <span>Menu</span>
            </button>
          </div>
        </div>
        {/* Row 2 (mobile only): filter input full width */}
        <div className="desktop:hidden mt-3">
          <FilterInput
            value={filter.raw}
            onChange={(raw) => setFilter(parseQuery(raw))}
          />
        </div>
      </header>

      {/* Mobile drawer: full-screen sheet with all secondary actions */}
      {mobileMenuOpen && (
        <MobileMenu
          user={user}
          allBoards={allBoards}
          currentBoardId={board.id}
          showMap={showMap}
          showAudit={showAudit}
          onSwitchBoard={(id) => {
            onSwitchBoard(id);
            setMobileMenuOpen(false);
          }}
          onToggleMap={() => {
            setShowMap((v) => !v);
            setMobileMenuOpen(false);
          }}
          onToggleAudit={() => {
            setShowAudit((v) => !v);
            setMobileMenuOpen(false);
          }}
          onNewTarget={() => {
            setShowNewTarget(true);
            setMobileMenuOpen(false);
          }}
          onLogout={() => {
            setMobileMenuOpen(false);
            void handleLogout();
          }}
          onClose={() => setMobileMenuOpen(false)}
        />
      )}

      <DndContext sensors={sensors} onDragStart={onDragStart} onDragEnd={onDragEnd}>
        {/* Per tw-6hud research: Chrome (uniquely) sizes the "fixed
            viewport" to the *minimum-scale rect*, so once page content
            has scrollWidth > clientWidth, Chrome inflates the layout
            viewport to fit it — and every `position: fixed` modal lands
            in that inflated space, off-screen. Worse: `overflow-x:
            hidden` on html/body is intentionally ignored by Chrome in
            this scenario (whatwg/compat#79), and `100vw` is the
            inflated value too, so it can't be its own bound.
            Empirically, `100dvw` resolves to the *visible* viewport on
            Chrome Android — using it for both the column widths AND
            the section's max-width keeps every descendant inside the
            visible viewport, so the document never inflates. min-w-0
            still does its job on desktop flex-row layout. */}
        <div className="px-3 desktop:px-6 pt-2">
          <HintCard id="kanban-drag" title="Move cards by dragging">
            Drag a card across columns to change its status. Approval-gated
            columns will prompt you for justification.
          </HintCard>
        </div>
        <main className="flex-1 flex flex-col desktop:flex-row min-h-0 max-w-[100dvw] desktop:max-w-none">
          <section
            className="flex-1 min-w-0 max-w-[100dvw] desktop:max-w-none overflow-x-auto p-3 desktop:p-6"
            style={
              // `contain: paint` is the non-negotiable bit for tw-6hud:
              // it promises the browser that descendants don't escape
              // this section's box for layout/paint purposes, so the
              // kanban's overflowing flex children stop bubbling up to
              // `documentElement.scrollWidth`. Without it, Chrome mobile
              // still sees scrollWidth > clientWidth and inflates the
              // fixed viewport. WITH it, document stays at clientWidth.
              showMap
                ? {
                    flexBasis: "60%",
                    flexGrow: 0,
                    flexShrink: 1,
                    contain: "paint",
                  }
                : { contain: "paint" }
            }
          >
            <div className="flex gap-3 desktop:gap-4 h-full snap-x snap-mandatory desktop:snap-none">
              {board.columns.map((c) => (
                <ColumnPanel
                  key={c.id}
                  column={c}
                  targets={byColumn.find((s) => s.columnId === c.id)?.targets ?? []}
                  board={board}
                  filter={filter}
                  flashIds={flashIds}
                  onSelect={setSelectedTarget}
                />
              ))}
            </div>
          </section>
          {showMap && byColumn.length > 0 && (
            <section
              // Desktop: split-pane next to kanban. Mobile: fullscreen
              // overlay so the map has room to actually breathe instead
              // of being squished under a column of cards.
              className="fixed top-0 left-0 w-[100dvw] h-[100dvh] z-40 desktop:static desktop:flex-1 desktop:min-w-0 desktop:border-l"
              style={{
                background: "var(--tw-bg)",
                borderColor: "var(--tw-border)",
              }}
            >
              <button
                onClick={() => setShowMap(false)}
                aria-label="Close map"
                className="desktop:hidden absolute top-3 left-3 z-50 tw-eyebrow text-[12px] px-3"
                style={{
                  background: "var(--tw-bg-panel)",
                  borderWidth: 1,
                  borderStyle: "solid",
                  borderColor: "var(--tw-border)",
                  borderRadius: "var(--tw-radius)",
                  color: "var(--tw-ink)",
                  minHeight: 44,
                }}
              >
                ← Back
              </button>
              <Suspense
                fallback={
                  <div
                    className="tw-eyebrow flex items-center justify-center h-full text-[11px]"
                    style={{ color: "var(--tw-ink-dim)" }}
                  >
                    Loading map…
                  </div>
                }
              >
                <MapPane
                  board={board}
                  targets={byColumn
                    .flatMap((s) => s.targets)
                    .filter((t) => matchesTarget(t, filter))}
                  selectedTargetId={selectedTarget?.id ?? null}
                  onSelectTarget={setSelectedTarget}
                />
              </Suspense>
            </section>
          )}
        </main>
        <DragOverlay dropAnimation={null}>
          {activeTarget ? (
            <TargetCard
              target={activeTarget}
              board={board}
              onClick={() => {}}
              asOverlay
            />
          ) : null}
        </DragOverlay>
      </DndContext>

      {showAudit && (
        <aside
          className="border-t max-h-72 overflow-y-auto p-4"
          style={{
            borderColor: "var(--tw-border)",
            background: "color-mix(in srgb, var(--tw-bg) 92%, transparent)",
          }}
        >
          <p
            className="tw-eyebrow text-[10px] mb-3"
            style={{ color: "var(--tw-brand)" }}
          >
            Workspace audit log
          </p>
          <ul className="space-y-1 text-xs" style={{ fontFamily: "var(--tw-font-mono)" }}>
            {audit.map((e) => (
              <li
                key={e.id}
                className="flex gap-3 p-2"
                style={{
                  borderWidth: 1,
                  borderStyle: "solid",
                  borderColor: "var(--tw-border)",
                  borderRadius: "var(--tw-radius)",
                  background: "var(--tw-bg-panel)",
                }}
              >
                <span style={{ color: "var(--tw-ink-dim)" }}>
                  {new Date(e.occurred_at).toLocaleTimeString()}
                </span>
                <span
                  className="tw-eyebrow text-[10px]"
                  style={{ color: "var(--tw-accent)" }}
                >
                  {e.event_type}
                </span>
                <span className="truncate" style={{ color: "var(--tw-ink-muted)" }}>
                  {e.justification ?? ""}
                </span>
              </li>
            ))}
            {audit.length === 0 && (
              <li className="italic" style={{ color: "var(--tw-ink-dim)" }}>
                No events yet — create a target and move it.
              </li>
            )}
          </ul>
        </aside>
      )}

      {showNewTarget && (
        <NewTargetForm
          board={board}
          onCreated={() => {
            setShowNewTarget(false);
            void refresh();
          }}
          onCancel={() => setShowNewTarget(false)}
        />
      )}

      {selectedTarget && (
        <TargetDetail
          target={selectedTarget}
          board={board}
          onClose={() => setSelectedTarget(null)}
          onMoved={() => {
            setSelectedTarget(null);
            void refresh();
          }}
        />
      )}

      {pending && (
        <ApprovalPrompt
          target={pending.target}
          toColumn={pending.toColumn}
          board={board}
          onCancel={() => {
            // User bailed — undo the optimistic move by resyncing.
            setPending(null);
            void refresh();
          }}
          onConfirm={(approvingRole, justification) => {
            const p = pending;
            setPending(null);
            void performMove(p.target, p.toColumn.id, p.fromColumnId, {
              approvingRole,
              justification: justification ?? undefined,
            });
          }}
        />
      )}

      {showBoardEdit && (
        <BoardEditForm
          board={board}
          onSaved={async () => {
            setShowBoardEdit(false);
            await onBoardsChanged();
          }}
          onDeleted={async () => {
            setShowBoardEdit(false);
            await onBoardsChanged();
          }}
          onCancel={() => setShowBoardEdit(false)}
        />
      )}

      {showNewBoard && (
        <NewBoardForm
          onCreated={async () => {
            setShowNewBoard(false);
            await onBoardsChanged();
          }}
          onCancel={() => setShowNewBoard(false)}
        />
      )}
    </div>
  );
}

function isCommanderOrAdmin(role: string): boolean {
  return role === "commander" || role === "admin";
}

function FilterInput({
  value,
  onChange,
}: {
  value: string;
  onChange: (raw: string) => void;
}): React.JSX.Element {
  return (
    <div className="relative">
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Filter — bison · cot:a-h · qual:confirmed · track:active"
        aria-label="Filter targets"
        className="w-full px-3 py-1.5 text-sm pr-8"
        style={{
          background: "var(--tw-bg)",
          borderWidth: 1,
          borderStyle: "solid",
          borderColor: "var(--tw-border)",
          borderRadius: "var(--tw-radius)",
          color: "var(--tw-ink)",
          fontFamily: "var(--tw-font-body)",
          minHeight: 44,
        }}
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label="Clear filter"
          className="absolute right-2 top-1/2 -translate-y-1/2 text-[14px]"
          style={{ color: "var(--tw-ink-dim)" }}
        >
          ×
        </button>
      )}
    </div>
  );
}

function LiveIndicator({
  status,
  compact = false,
}: {
  status: "connecting" | "open" | "closed";
  compact?: boolean;
}): React.JSX.Element {
  // Renamed the user-facing label from "LIVE" → "ONLINE" so it doesn't
  // collide semantically with the per-target age counter (the user was
  // confused by what "LIVE" meant on cards; freeing this label for the
  // WS-stream status keeps it unambiguous now that target cards no
  // longer carry a LIVE word).
  const color =
    status === "open"
      ? "var(--tw-accent)"
      : status === "connecting"
        ? "var(--tw-approval)"
        : "var(--tw-ink-dim)";
  const label =
    status === "open"
      ? "ONLINE"
      : status === "connecting"
        ? "SYNCING"
        : "OFFLINE";
  return (
    <span
      className="tw-eyebrow inline-flex items-center gap-2 text-[10px]"
      title={`Realtime stream: ${status}`}
      style={{ color: "var(--tw-ink-muted)" }}
    >
      <span
        aria-hidden
        style={{
          width: 7,
          height: 7,
          borderRadius: 999,
          background: color,
          boxShadow: status === "open" ? `0 0 6px ${color}` : "none",
          display: "inline-block",
        }}
      />
      {!compact && label}
    </span>
  );
}

function MobileMenu({
  user,
  allBoards,
  currentBoardId,
  showMap,
  showAudit,
  onSwitchBoard,
  onToggleMap,
  onToggleAudit,
  onNewTarget,
  onLogout,
  onClose,
}: {
  user: UserOut;
  allBoards: Board[];
  currentBoardId: string;
  showMap: boolean;
  showAudit: boolean;
  onSwitchBoard: (id: string) => void;
  onToggleMap: () => void;
  onToggleAudit: () => void;
  onNewTarget: () => void;
  onLogout: () => void;
  onClose: () => void;
}): React.JSX.Element {
  return (
    <div
      className="fixed top-0 left-0 w-[100dvw] h-[100dvh] desktop:left-auto desktop:right-4 desktop:top-16 desktop:w-[360px] desktop:h-auto desktop:max-h-[calc(100dvh-5rem)] z-50 flex flex-col"
      style={{ background: "color-mix(in srgb, var(--tw-bg) 96%, transparent)" }}
      role="dialog"
      aria-modal="true"
      aria-label="Menu"
    >
      <header
        className="px-4 py-3 border-b flex items-center justify-between"
        style={{ borderColor: "var(--tw-border)" }}
      >
        <p className="tw-eyebrow text-[11px]" style={{ color: "var(--tw-brand)" }}>
          Menu
        </p>
        <button
          onClick={onClose}
          aria-label="Close menu"
          className="text-[18px]"
          style={{
            color: "var(--tw-ink-muted)",
            minWidth: 44,
            minHeight: 44,
          }}
        >
          ✕
        </button>
      </header>
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        <button
          onClick={onNewTarget}
          className="w-full tw-eyebrow text-[12px] px-4 py-3"
          style={{
            background: "var(--tw-accent-bg)",
            color: "var(--tw-accent-ink)",
            borderRadius: "var(--tw-radius)",
            minHeight: 52,
          }}
        >
          + New Target
        </button>
        {allBoards.length > 1 && (
          <label className="block space-y-1">
            <span
              className="tw-eyebrow text-[10px]"
              style={{ color: "var(--tw-ink-dim)" }}
            >
              Board
            </span>
            <select
              value={currentBoardId}
              onChange={(e) => onSwitchBoard(e.target.value)}
              className="w-full px-3 py-2 text-sm"
              style={{
                background: "var(--tw-bg-panel)",
                borderWidth: 1,
                borderStyle: "solid",
                borderColor: "var(--tw-border)",
                borderRadius: "var(--tw-radius)",
                color: "var(--tw-ink)",
                minHeight: 52,
              }}
            >
              {allBoards.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <MenuRow
          label={showMap ? "Hide map" : "Show map"}
          onClick={onToggleMap}
        />
        <MenuRow
          label={showAudit ? "Hide audit log" : "Show audit log"}
          onClick={onToggleAudit}
        />
        <a
          href="/settings"
          onClick={onClose}
          className="block w-full text-left tw-eyebrow text-[12px] px-4 py-3"
          style={{
            background: "var(--tw-bg-panel)",
            borderWidth: 1,
            borderStyle: "solid",
            borderColor: "var(--tw-border)",
            borderRadius: "var(--tw-radius)",
            color: "var(--tw-ink)",
            minHeight: 52,
          }}
        >
          Account & Security
        </a>
        <a
          href="/settings"
          onClick={onClose}
          className="block w-full text-left tw-eyebrow text-[12px] px-4 py-3"
          style={{
            background: "var(--tw-bg-panel)",
            borderWidth: 1,
            borderStyle: "solid",
            borderColor: "var(--tw-border)",
            borderRadius: "var(--tw-radius)",
            color: "var(--tw-ink)",
            minHeight: 52,
          }}
        >
          Settings
        </a>
      </div>
      <footer
        className="px-4 py-3 border-t flex items-center justify-between"
        style={{ borderColor: "var(--tw-border)" }}
      >
        <div
          className="text-xs leading-tight"
          style={{ color: "var(--tw-ink-muted)" }}
        >
          <div style={{ fontFamily: "var(--tw-font-body)" }}>{user.email}</div>
          <div
            className="tw-eyebrow text-[9px]"
            style={{ color: "var(--tw-ink-dim)" }}
          >
            {user.role}
          </div>
        </div>
        <button
          onClick={onLogout}
          className="tw-eyebrow text-[11px] px-3"
          style={{
            color: "var(--tw-ink-muted)",
            borderWidth: 1,
            borderStyle: "solid",
            borderColor: "var(--tw-border)",
            borderRadius: "var(--tw-radius)",
            minHeight: 44,
            minWidth: 44,
          }}
        >
          Logout
        </button>
      </footer>
    </div>
  );
}

function MenuRow({
  label,
  onClick,
}: {
  label: string;
  onClick: () => void;
}): React.JSX.Element {
  return (
    <button
      onClick={onClick}
      className="w-full text-left tw-eyebrow text-[12px] px-4 py-3"
      style={{
        background: "var(--tw-bg-panel)",
        borderWidth: 1,
        borderStyle: "solid",
        borderColor: "var(--tw-border)",
        borderRadius: "var(--tw-radius)",
        color: "var(--tw-ink)",
        minHeight: 52,
      }}
    >
      {label}
    </button>
  );
}

interface ColumnPanelProps {
  column: Board["columns"][number];
  targets: Target[];
  board: Board;
  filter: FilterSpec;
  flashIds: Set<string>;
  onSelect: (t: Target) => void;
}

function ColumnPanel({
  column,
  targets,
  board,
  filter,
  flashIds,
  onSelect,
}: ColumnPanelProps): React.JSX.Element {
  const matchCount = useMemo(
    () =>
      filter.terms.length === 0
        ? targets.length
        : targets.filter((t) => matchesTarget(t, filter)).length,
    [targets, filter],
  );
  const { isOver, setNodeRef } = useDroppable({
    id: `column-${column.id}`,
    data: { type: "column", columnId: column.id },
  });

  const dropHint = useMemo(
    () => (column.requires_approval ? "var(--tw-approval)" : "var(--tw-accent)"),
    [column.requires_approval],
  );

  return (
    <section
      className="w-[88dvw] min-w-[88dvw] desktop:w-72 desktop:min-w-[18rem] flex flex-col transition-colors snap-start"
      style={{
        background: isOver
          ? "color-mix(in srgb, var(--tw-bg-panel) 70%, transparent)"
          : "color-mix(in srgb, var(--tw-bg-panel) 55%, transparent)",
        borderWidth: isOver ? 2 : 1,
        borderStyle: isOver ? "dashed" : "solid",
        borderColor: isOver ? dropHint : "var(--tw-border)",
        borderRadius: "var(--tw-radius)",
      }}
    >
      <header
        className="px-3 py-2.5 flex items-center justify-between gap-2 border-b"
        style={{ borderColor: "var(--tw-border)" }}
      >
        <div className="min-w-0">
          <div
            className="tw-eyebrow text-[11px] truncate"
            style={{ color: "var(--tw-ink)" }}
          >
            {column.name}
          </div>
          {column.requires_approval && (
            <div
              className="tw-eyebrow text-[9px] mt-0.5"
              style={{ color: "var(--tw-approval)", letterSpacing: "0.18em" }}
            >
              approval required
            </div>
          )}
        </div>
        <div
          className="text-[11px]"
          style={{
            color: "var(--tw-ink-muted)",
            fontFamily: "var(--tw-font-mono)",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {filter.terms.length > 0
            ? `${matchCount.toString().padStart(2, "0")} / ${targets.length
                .toString()
                .padStart(2, "0")}`
            : targets.length.toString().padStart(2, "0")}
        </div>
      </header>
      <div
        ref={setNodeRef}
        className="flex-1 p-2 space-y-2 overflow-y-auto"
        style={{ minHeight: 88 }}
      >
        {/* SortableContext gives @dnd-kit per-column ordering. Cards
            inside the same context can be dragged to swap positions;
            cards dragged across contexts cross-column-move. */}
        <SortableContext
          items={targets.map((t) => t.id)}
          strategy={verticalListSortingStrategy}
        >
          {targets.map((t) => {
            const matched = matchesTarget(t, filter);
            return (
              <div
                key={t.id}
                style={{
                  opacity: matched ? 1 : 0.1,
                  pointerEvents: matched ? "auto" : "none",
                  transition: "opacity 120ms ease-out",
                }}
                aria-hidden={!matched}
              >
                <TargetCard
                  target={t}
                  board={board}
                  onClick={() => onSelect(t)}
                  flash={flashIds.has(t.id)}
                />
              </div>
            );
          })}
        </SortableContext>
        {targets.length === 0 && (
          <div
            className="tw-eyebrow text-[10px] px-2 py-3 text-center"
            style={{ color: "var(--tw-ink-dim)" }}
          >
            — empty —
          </div>
        )}
      </div>
    </section>
  );
}
