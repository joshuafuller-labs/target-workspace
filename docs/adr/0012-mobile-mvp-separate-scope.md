# ADR 0012 — Mobile experience is a separate MVP scope

**Status:** Accepted
**Date:** 2026-05-16

## Context

Mobile responsiveness ([ADR 0011](0011-responsive-design.md)) is necessary but not sufficient. Field operators on phones have **fundamentally different needs** from desk-bound users:

- One-handed capture under time pressure
- GPS / camera / sensor auto-fill
- Offline-first with sync-when-connected
- Push notifications for state changes
- Battery anxiety, gloved hands, sun glare, intermittent connectivity
- Reduced surface area (capture + view, not deep workflow)

A single frontend "responsively shrunk" to phone size inevitably under-serves both audiences.

## Decision

**The mobile experience is a sibling MVP** to the desktop MVP — same backend, same data model, same plugin contracts, but its own scope, personas, user stories, journeys, mockups, and acceptance criteria. Tracked separately.

**Mobile MVP "done" definition (initial):** a field user pulls out their phone, logs in, captures a target with camera + GPS auto-filled, sees it sync to the workspace, gets notified when state changes, can view the kanban + map without the full admin/workflow controls, and works offline with sync-when-connected.

**Mobile MVP gets its own:**
- `docs/mobile-mvp-scope.md` (separate from `docs/mvp-scope.md`)
- Persona profiles (derived from existing roster but filtered/refined for mobile primary use)
- Journey maps (mobile-specific friction modeled — gloves, sun, batteries, connectivity)
- User stories with acceptance criteria
- Mockups in `docs/mockups/mobile/` (focused-mode designs, not desktop-responsive variants)

**Mobile-only first-class features:**
- Camera capture into Target
- GPS auto-fill for location
- Push notifications
- Offline-first sync
- Single-handed thumb-zone UI
- Voice capture for notes
- ATAK plugin as an alternative mobile client path entirely (Java/Kotlin, distributed separately)

## Sequencing

**Not parallel-from-day-1, but planned-parallel-from-day-1.** Desktop MVP proves the backend architecture. Mobile MVP follows, leveraging the proven architecture and plugin contracts.

The desktop MVP must NOT make architectural decisions that preclude mobile MVP — see [ADR 0013](0013-api-client-agnostic.md) for the API-shape commitment that protects this option.

## Architectural enablers in desktop MVP (so mobile MVP is cheap)

- API surface fully consumable by an unauthenticated mobile-first client; see [ADR 0013](0013-api-client-agnostic.md)
- Offline-first sync semantics get a placeholder in the data model (server-issued IDs, monotonic version/etag per object, conflict-resolution hooks) even though desktop MVP doesn't need them
- Capture-focused endpoints (e.g., `POST /v1/capture` with photo + GPS + minimal Target schema) sketched so mobile doesn't have to invent its own ingestion path
- The four flagship HTML mockups are explicitly desktop example themes — NOT a starting point for mobile

## Consequences

**Wins:**
- Field operators served by a focused experience, not a shrunken desktop
- Each MVP has a sharper "done" definition
- Each gets dedicated demo capability (per [ADR 0010](0010-demo-capability-post-mvp.md))
- Plugin architecture pays a dividend — two clients, one backend

**Trade-offs accepted:**
- More PM work (two scope docs, two persona sets, two demo paths)
- Risk of architectural over-fitting if either MVP is built without the other in mind — mitigated by [ADR 0013](0013-api-client-agnostic.md)
- More frontend code overall (focused mobile client + responsive desktop SPA), but no shared-but-bad compromise frontend

## References

- [ADR 0008 — Malleability principle](0008-malleability-principle.md)
- [ADR 0011 — Responsive design](0011-responsive-design.md)
- [ADR 0013 — API client-agnostic](0013-api-client-agnostic.md)
- Agent memory: `feedback_target_workspace_mobile_mvp.md`
