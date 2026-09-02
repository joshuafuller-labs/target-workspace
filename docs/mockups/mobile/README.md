# Mobile MVP — Focused-mode mockups

ASCII / Unicode wireframes for the mobile MVP, sized for a 390-wide
phone portrait viewport. NOT desktop-responsive variants — different
information architecture, different surface area.

Per `docs/mobile-mvp-scope.md` and `docs/personas/mobile.md`.

## Screen 1 — App shell (sync chip always visible)

```
┌──────────────────────────────────┐
│ ☰   Target Workspace   [synced]  │  ← chrome bar with sync chip
├──────────────────────────────────┤
│                                  │
│         ┌──────────────┐         │
│         │   📷 CAPTURE  │         │  ← thumb-zone primary action
│         └──────────────┘         │     full-width, ≥ 44px
│                                  │
│  Recent captures:                │
│  ┌──────────────────────────┐    │
│  │ ⏳ "F adult, blue jacket" │    │  ← in-flight
│  │   142 Oak St · 30s ago   │    │
│  └──────────────────────────┘    │
│  ┌──────────────────────────┐    │
│  │ ✓  "Flooded structure"    │    │
│  │   Main+5th · 4m ago      │    │
│  └──────────────────────────┘    │
│                                  │
├──────────────────────────────────┤
│  [Captures]  [Tasks]   [Map]     │  ← bottom tab bar
└──────────────────────────────────┘
```

## Screen 2 — Capture flow (camera-first)

```
┌──────────────────────────────────┐
│  [← Cancel]              [syncing 2] │
├──────────────────────────────────┤
│  ┌──────────────────────────┐    │
│  │                          │    │
│  │                          │    │
│  │     ┌──────────────┐    │    │
│  │     │ CAMERA VIEW  │    │    │  ← live preview
│  │     │              │    │    │     fills most of screen
│  │     │              │    │    │
│  │     └──────────────┘    │    │
│  │                          │    │
│  │            ◯              │    │  ← shutter, large
│  └──────────────────────────┘    │
│                                  │
│  📍 GPS: 35.602° N  82.555° W    │  ← live GPS chip
│      (acquired 2s ago)           │
└──────────────────────────────────┘
```

After shutter, transitions to:

```
┌──────────────────────────────────┐
│  [← Retake]              [syncing 2] │
├──────────────────────────────────┤
│  ┌──────────────────────────┐    │
│  │   [photo thumbnail]      │    │
│  └──────────────────────────┘    │
│                                  │
│  Title  ┌─────────────────────┐  │
│         │ F adult mid-50s     │  │  ← single text input
│         │ blue jacket         │  │
│         └─────────────────────┘  │
│                                  │
│  📍 35.602° N  82.555° W         │  ← read-only GPS
│  📋 Auto-board: SAR · Search     │  ← server-suggested
│                                  │
│         ┌──────────────┐         │
│         │   SUBMIT      │         │  ← full-width
│         └──────────────┘         │
│                                  │
└──────────────────────────────────┘
```

## Screen 3 — Card detail (from a push notification)

```
┌──────────────────────────────────┐
│  [← Back]    SAR-12     [synced]  │
├──────────────────────────────────┤
│                                  │
│  Needs Decision                  │  ← state chip, prominent
│                                  │
│  F adult, mid-50s, blue jacket   │  ← title
│  Last seen: 142 Oak St           │
│                                  │
│  ┌──────────────────────────┐    │
│  │   [map dot at location]   │    │  ← tap to expand map
│  │                          │    │
│  └──────────────────────────┘    │
│                                  │
│  Audit excerpt:                  │
│   0723L · @captain — gate hit    │
│   0701L · @field42 — captured    │
│   ...                            │
│                                  │
│  Actions:                        │
│  ┌──────────────────────────┐    │
│  │ ✓ Continue Search         │    │
│  └──────────────────────────┘    │
│  ┌──────────────────────────┐    │
│  │ → Transition to Recovery  │    │
│  └──────────────────────────┘    │
│                                  │
└──────────────────────────────────┘
```

## Screen 4 — Expiry banner (Strike-Team Responder)

```
┌──────────────────────────────────┐
│ ☰   Target Workspace   [synced]  │
├──────────────────────────────────┤
│ ⏰ Access ends in 23h 47m         │  ← banner, dismissible
│   (Cajun Navy detachment)        │
│   [Extend] (request to coord.)   │
├──────────────────────────────────┤
│                                  │
│  ... normal app contents ...     │
│                                  │
└──────────────────────────────────┘
```

## Screen 5 — Sync tray (tap the chip)

```
┌──────────────────────────────────┐
│  [Close]    Sync queue    [now]   │
├──────────────────────────────────┤
│                                  │
│  Outgoing (2)                    │
│  ┌──────────────────────────┐    │
│  │ ⏳ POST /v1/capture        │    │
│  │   142 Oak — 'F adult'    │    │
│  │   waiting for network    │    │
│  └──────────────────────────┘    │
│  ┌──────────────────────────┐    │
│  │ ⏳ PATCH /v1/targets/...   │    │
│  │   move SAR-12 → Found    │    │
│  │   retry in 30s           │    │
│  └──────────────────────────┘    │
│                                  │
│  Errors (0)                      │
│                                  │
│  Last sync: 4 minutes ago        │
│  Pending bytes: 1.2 MB           │
│                                  │
└──────────────────────────────────┘
```

## Screen 6 — Offline state

```
┌──────────────────────────────────┐
│ ☰   Target Workspace [offline 3] │  ← chip
├──────────────────────────────────┤
│  ⚠ No network                    │
│  Captures will sync when you     │
│  return to coverage.             │
│                                  │
│         ┌──────────────┐         │
│         │   📷 CAPTURE  │         │  ← still works
│         └──────────────┘         │
│                                  │
│  3 captures pending sync.        │
│  Map: bundled tiles only.        │
│                                  │
└──────────────────────────────────┘
```

## Design rules these mockups encode

1. **Sync chip** is in the top-right of the chrome bar on EVERY screen.
2. **Primary action** is full-width, thumb-zone (bottom 33% of viewport).
3. **No hover affordances.** Anything actionable is tappable.
4. **Camera is the first thing the operator sees** when they tap Capture. No preflight modal, no "let's get started" copy.
5. **Audit excerpt on card detail** is visible without scrolling — operators glance at it during a call.
6. **All states have an offline equivalent** — the offline-pending count is the first thing you see in the chip.
7. **Two thumb-tap maximum** from app-cold-launch to first capture submitted. Anything more loses operator buy-in.

## What's NOT here (intentional)

- No kanban board view. Kanban authoring is desktop-only.
- No theme picker. Mobile uses the auto outdoor-light-mode toggle.
- No multi-board switcher. The mobile app is always scoped to the user's primary board(s); switching is a settings affair, not a per-screen toggle.
- No drag-drop. State changes happen via explicit action buttons.

## Open questions for the design phase

- Native bottom-sheet vs full-screen for sync tray? (Native is more iOS/Android-idiomatic.)
- Camera UI: in-app vs OS camera intent? (In-app is faster + auto-GPS; OS camera gives users the camera they know.)
- Push opt-in flow timing — at app first-launch vs after first successful capture?
