# Mobile MVP — Scope

This document is the **scope statement for the Mobile MVP**. It is intentionally separate from `docs/MVP_CUT_LIST.md` (the Desktop MVP scope).

Per [ADR 0012](adr/0012-mobile-mvp-separate-scope.md), mobile is a **sibling MVP, not a responsive desktop variant**. Different personas, different workflows, different launch.

## Done definition (one sentence)

A field user can stand up the mobile app, capture an observation with **camera + GPS** in <30 seconds even with intermittent connectivity, see the capture sync once the connection returns, and **receive a push notification** when a state change on a card they care about happens.

## In scope

- **Focused capture flow.** Title + photo + GPS + minimum-viable metadata, no kanban view. The mobile app is a capture device, not a board editor.
- **Offline-first.** Captures queue locally on the device, retry-with-backoff when the network returns. Per `tw-2j9` ETag/If-Match on the backend gives the offline-sync substrate.
- **Push notifications** on state changes for cards the user is assigned to (post-MVP-server-side covers the trigger seam via `tw-ngn5`; the push channel itself is mobile-specific work).
- **Authentication via session cookie OR bearer token.** Bearer is the mobile-friendly path (`tw-sodu` shipped the table; the mobile client uses a long-lived service-account-style token or device-bound session).
- **Minimum-viable map.** Static raster tiles (`tw-45s` override mechanism) — no Cesium globe on a phone.
- **Two responsive layouts** — phone portrait, phone landscape. No tablet.

## Out of scope

- **Full kanban view on phone.** That's a responsive-desktop pattern; we explicitly rejected it.
- **Native Cesium 3D globe.** Too heavy for a phone GPU + bandwidth budget.
- **Drag-and-drop column moves.** Mobile uses an explicit move action; finger drag conflicts with scroll.
- **All board admin** (column edit, theme, RBAC management) — that's a desktop concern. Per `tw-itn` etc.
- **Map overlays for analyst use.** Mobile is for capture + acknowledgment, not exploration.

## Personas (sibling profiles, not desktop derivatives)

- **Field operator** — capturing observations, mostly outside, on a phone, with intermittent cell. Most common.
- **Strike-team responder** — Helene-shape Cajun Navy detachment or USAR Tennessee team rolling in. Time-bound access via `tw-6to0` + group membership via `tw-icj8`.
- **Public-safety captain** — receives pages on state change, taps to acknowledge. Doesn't author content on mobile; does on desktop.

## Architectural enablers (already in desktop MVP)

These ride in desktop MVP per foundation §15 specifically so mobile MVP is cheap when it lands:

- `tw-bux` POST /v1/capture multipart endpoint
- `tw-2j9` ETag / If-Match on targets
- `tw-cjk` `since=<iso>` query on /v1/audit for offline-sync resume
- `tw-icj8` workspace groups schema
- `tw-6to0` time-bound user access
- `tw-sodu` API tokens (bearer auth)
- `tw-45s` map tile URL override

## Tickets in the Mobile MVP epic

Tracked under `tw-h6s` (Mobile MVP epic):

- `tw-31n` — Mobile user stories + acceptance criteria
- `tw-4wu` — Mobile-primary persona profiles (formal write-ups of the personas above)
- `tw-9th` — Mobile mockups (focused-mode designs)
- `tw-afy` — Mobile journey maps
- `tw-m55` — Mobile client implementation (PWA or native — to be decided)
- This document (`tw-7qf`)

## Launch criteria

Mobile MVP ships when:

1. A field user can complete the capture flow above end-to-end on iOS Safari + Chrome Android.
2. Round-trip: capture offline, plane lands, network returns → capture posts within the auto-retry window.
3. Push notifications work on both major platforms (web-push for PWA, APNs/FCM for native).
4. The same backend (no per-mobile API surface) handles both desktop SPA and mobile client.

## Status note

Mobile MVP work has not yet started. The desktop MVP (`tw-kdx1`) is complete as of 2026-05-18. Next decision: PWA vs. native React Native vs. native iOS/Android.
