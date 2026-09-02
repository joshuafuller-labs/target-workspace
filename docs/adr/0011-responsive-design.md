# ADR 0011 — Responsive design across phone, foldable, tablet, desktop

**Status:** Accepted
**Date:** 2026-05-16

## Context

The four flagship HTML mockups were desktop-only — fixed-pixel grid templates (`grid-cols-[260px_minmax(0,1fr)_400px]`) that collapsed on a Pixel Fold (validated empirically via Playwright at 720×1024 and 1024×720 — the center column compressed to 0–52px, board columns crushed to single digits). That was acceptable for example themes but **not acceptable for production code**.

Operators on this product carry phones in tactical pouches, use ruggedized handhelds in patrol cars, run tablets vehicle-mounted in landscape, fold devices unfold to tablet form factor. A desktop-only product is dead on arrival.

## Decision

**Every production UI surface is responsive.** Specifically:

- **Both orientations supported** — landscape and portrait variants behave correctly; layouts collapse vertically below a width threshold (~900px is the rough breakpoint) and reflow horizontally above.
- **No fixed-pixel grid templates in production code.** `grid-cols-[NNNpx_…]` and equivalent patterns are forbidden. Use CSS Grid `repeat(auto-fit, minmax(<min>, 1fr))` or container queries.
- **Touch-first interactions.** Drag-drop works via touch; hit targets ≥ 44px; no hover-only affordances; long-press for context menus where right-click is conventional on desktop.
- **Cesium 2D mode default on mobile viewports.** 3D is heavy on phone GPUs; the toggle exists but the default per-viewport is responsive.
- **Foldable-aware.** Inner unfolded display behaves like a small tablet; cover display behaves like a phone. Use Viewport Segments API (where available) for hinge-aware layouts.
- **Tested at multiple viewports in CI.** Playwright tests run at: 360×800, 412×915, 720×1024, 1024×720, 1440×900, 1920×1080. Horizontal-overflow + crushed-grid + sibling-overlap detection (the script we built at `/tmp/review_fold.py` is the template).

## Scope

This ADR is the **technical responsive baseline**. It applies to every production UI surface — including the desktop SPA, the mobile MVP surface ([ADR 0012](0012-mobile-mvp-separate-scope.md)), bundled themes, and community themes.

The four flagship HTML mockups in `docs/mockups/` are **example desktop themes only**, not production code, and are explicitly exempt from this ADR per [ADR 0008](0008-malleability-principle.md).

## Consequences

**Wins:**
- Field operators get a working experience without "this is a desktop product, sorry"
- Foldables and tablets handled correctly from day one
- Visual-regression CI catches grid-collapse class of bugs before they ship

**Trade-offs accepted:**
- Frontend complexity grows — every component needs responsive consideration
- Cesium tuning effort larger (mobile GPU profile)
- More CI runtime for viewport-matrix tests

## References

- [ADR 0003 — Frontend stack](0003-react-vite-resium-stack.md)
- [ADR 0008 — Malleability principle](0008-malleability-principle.md)
- [ADR 0012 — Mobile MVP separate scope](0012-mobile-mvp-separate-scope.md)
- Agent memory: `feedback_target_workspace_responsive.md`
