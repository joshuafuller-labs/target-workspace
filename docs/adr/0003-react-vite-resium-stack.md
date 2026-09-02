# ADR 0003 — Frontend stack: React 19 + Vite + TypeScript + Resium

**Status:** Accepted
**Date:** 2026-05-16

## Context

The UI must integrate cleanly with CesiumJS (locked for MVP per [ADR 0004](0004-cesium-map-pane-in-mvp.md)), support a kanban with drag-and-drop, and remain malleable so a workspace owner can re-theme without touching the framework.

## Decision

- **React 19** + **React DOM** (MIT)
- **TypeScript 6.0.3** with strict everything (no `any` without comment, `noUncheckedIndexedAccess`, etc.)
- **Vite 8.0.13** (post CVE-2026-39363/4/5)
- **Resium 1.20** for React + CesiumJS bindings (most mature React-Cesium binding in 2026)
- **Tailwind 4** for utility styling
- **shadcn/ui** for components (copy-paste model — no npm dependency on the components themselves; maximum customizability fits malleability principle)
- **TanStack Query 5** for server state, **Zustand 5** for client UI state

Pinned versions in [docs/tech-stack.md §E](../tech-stack.md).

## Consequences

**Wins:**
- React-Cesium integration via Resium is the most documented + maintained path
- TypeScript strict mode catches the same class of bugs `mypy --strict` catches on the backend
- shadcn/ui's copy-paste model means we own and can theme every component
- Same language (TS) eventually if/when adapters extend client-side

**Trade-offs accepted:**
- React 19's compiler is opt-in; we accept default behavior for MVP
- Tailwind 4 is a recent (2026) major; we adopt cleanly rather than supporting 3.x
- Vite + Cesium needs `manualChunks` config so the ~6MB Cesium bundle is separate from the app shell

## References

- [docs/tech-stack.md §E](../tech-stack.md)
- https://resium.reearth.io/
- [ADR 0011 — Responsive design](0011-responsive-design.md) — every production UI built with this stack is responsive
- [ADR 0012 — Mobile MVP separate scope](0012-mobile-mvp-separate-scope.md) — the desktop SPA is one frontend; mobile gets its own focused client
