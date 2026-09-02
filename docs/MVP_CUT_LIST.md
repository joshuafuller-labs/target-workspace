# MVP Cut List

The authoritative scope for **Desktop MVP v1.0** (bd: `tw-kdx1`). Anything not on this list is post-MVP.

> **Launch definition.** A single operator can stand up one instance, run a multi-board workspace through one full operational period end-to-end — with production-grade auth + audit + CoT-IN + CoT-OUT + Cesium map + realtime kanban — and recover from data loss.

Cross-references: `docs/foundation.md` §17 (explicitly deferred items), `docs/adr/0010-demo-capability-post-mvp.md`, `docs/adr/0012-mobile-mvp-separate-scope.md`.

## How to use this document

The bd label `mvp` is the live source: `bd list -l mvp` returns this exact set. This doc is a human-readable mirror with rationale. When the two disagree, the bd label wins and this doc gets updated.

## What ships in MVP

### Pre-code decisions (P0 — gate downstream work)

Each must produce an ADR before any dependent code lands.

- `tw-eo6l` — **Multi-org model**: groups-in-workspace vs full multi-tenancy. Foundation says multi-tenancy out of MVP; the Helene reframe (sub-orgs sharing one instance) re-opened the question.
- `tw-a3ix` — **Federation transport**: piggyback on TAK federation vs separate plane vs hybrid. Decision changes schema, auth, and deployment.
- `tw-n0b4` — **Sharpen tw-v8s scope**: shared-identity + per-board state model, unifying local Send-to-board with cross-instance Send-to-peer.
- `tw-ed8u` — **ICS scope**: is ICS-as-real-feature in MVP or v1.x? Three options (full / theme-only / hybrid). Resolution determines if the ICS epic children (`tw-eebq`, `tw-l40z`, `tw-vem9`) inherit the `mvp` label.

### Auth chain (parent epic: `tw-dlw6`)

- `tw-4exk` — Force password change on first login (admin-provisioned accounts)
- `tw-6llq` — Auth telemetry / login audit log
- `tw-qj9k` — Password reset (pluggable email backend, console default, SMTP stub)
- `tw-gmq7` — Account lockout after N failed attempts
- `tw-b3bi` — Rate-limit auth endpoints (login / reset / MFA)
- `tw-ptn2` — Session management: timeout, refresh, revoke-all
- `tw-6to0` — Time-bound user access (`expires_at` on user + group_member). Required for Helene strike-team scenario.
- `tw-qmnh` — Invitation flow (coordinator-mintable join tokens). Sub-org coordinator self-service.

### Schema enablers — slots ship in MVP so post-MVP features compose without migrations

- `tw-v8s` — Cross-board target linking. **Schema portion only**; Send-to-board UX deferred.
- `tw-liwf` — Per-resource RBAC. **Data-model hooks only**; admin UI deferred.
- `tw-icj8` — Workspace groups (sub-org abstraction). Gated by `tw-eo6l`.
- `tw-16c0` — Signed audit events with peer-id slot. Cross-instance ingest deferred; the schema and per-instance ed25519 keypair are MVP.
- `tw-2j9` — API/data offline-first sync semantics. Foundation §15 mobile-MVP enabler.

### UX gaps blocking "one operator runs end-to-end"

- `tw-ypfy` — Settings page: Security + Users + Tokens tabs
- `tw-itn` — Column add/edit/delete on existing boards

### Brand-promise / plugin seams

- `tw-50i5` — CoT-OUT publisher pipeline. Plugin contract + first publisher. Closes the half-built CoT-native promise.
- `tw-ngn5` — Notification trigger seam. Audit pipeline fans out to registered triggers. **No specific channels at MVP** (no SMTP/Slack/PagerDuty) — those compose on the seam in v1.1.

### Operational primitives

- `tw-b0ky` — Backup / export snapshot. Defensible answer to "SQLite corrupts mid-incident."
- `tw-45s` — Bundled offline Natural Earth tiles + override.

### Foundation §15 mobile-MVP architectural enablers (ride in desktop MVP)

- `tw-bux` — POST /v1/capture endpoint (mobile-friendly target capture).
- `tw-cjk` — Offline-first sync hardening for field comms breakdown.
- `tw-ddt` — API enabler: POST /v1/capture (mobile-MVP epic child; serves desktop too).

### Source adapters (parent epic: `tw-2tn`)

Already shipped within this epic:

- HTTP webhook source (`tw-h7x`)
- CoT-in TCP listener (`tw-o13`)

First three sources is the foundation-level cut; one more remains to round it out (TBD per source adapter scope).

### Process

- `tw-z3kr` — This document. The bd `mvp` label is the live source; this doc explains the rationale.

## What ships post-MVP (and why)

### Demo capability (`tw-1ks` epic + children)

Per [ADR 0010](adr/0010-demo-capability-post-mvp.md): without a committed pilot, the demo IS the product validation tool — but the *features* (replay engine, guided tour, session capture) ship after MVP. The *architectural enablers* (injectable clock, signed audit events) ride in MVP.

### Mobile MVP (`tw-h6s` epic + children)

Per [ADR 0012](adr/0012-mobile-mvp-separate-scope.md): mobile is a sibling MVP, not a responsive variant. Same backend; different focused frontend with its own personas, stories, journeys, and scope. Separate launch.

### Federation features (beyond schema slots)

- `tw-aoo` Effector plugin contract — post-MVP per project memory.
- `tw-12l` Effector implementation — post-MVP.
- `tw-gut` tw_mesh federation publisher — post-MVP.
- Cross-instance audit reassembly, peer discovery, store-and-forward — all post-MVP. Schema slots (`tw-16c0`) make later retrofit cheap.

### Full identity / MFA stack

Auth seam ships at MVP; integrations don't:

- `tw-phe` Authlib OIDC plugin
- `tw-mg1a` TOTP MFA + recovery codes
- `tw-kq7z` WebAuthn / passkey support
- `tw-sodu` API tokens for service accounts
- `tw-r1ru` MFA enforcement policy
- `tw-huzu` Suspicious-login signals

### Advanced features (real but not v1-blocking)

- `tw-swl` Multi-board N-up view — workaround: open multiple browser tabs
- `tw-j3x6` Bulk target import
- `tw-auf` Entity-type pluralism (target ≠ adversary contact)
- `tw-17o` Person-by-name workflow + reunification graph
- `tw-5gw` Task ↔ resource matching engine
- `tw-xj4` Editable target geometry in SPA (drag, ellipse/polygon edit)
- `tw-z9g` Board templates + clone-from-board
- `tw-1csv` First-run admin setup wizard
- `tw-jxl` First-run scenario picker / empty-state

### Polish

- `tw-13a` Cursor pagination + filter/sort syntax
- `tw-33g` RFC 7807 Problem Details errors
- `tw-54t` Idempotency-Key header support on POST

### ICS features (conditional on `tw-ed8u`)

If `tw-ed8u` resolves to "ICS is MVP" (option A or hybrid C), pull these into MVP individually:

- `tw-eebq` Operational period as first-class concept (subsumes `tw-zkki`)
- `tw-l40z` ICS-position-based authority
- `tw-vem9` ICS-214 Activity Log export — the cheapest win
- `tw-5hq` Full ICS form export (204/214/209)
- `tw-qkp` ICS-211 resource accountability
- `tw-fgz` FEMA PDA damage assessment

If `tw-ed8u` resolves to "ICS is theme-only" (option B), the whole `tw-13il` epic moves out of MVP and the marketing should match.

### Marketing / process / non-feature

- `tw-4ty` Animated walkthrough video — marketing
- `tw-91t` Pilot / design partner — process
- `tw-y60` Playwright viewport-matrix tests — superseded by `tests/e2e/responsive.spec.ts` shipped 2026-05-17
- `tw-7xk` Fix mutmut config — internal tooling

## Rules for new tickets

1. **Every new bd ticket gets classified at filing time** as one of `mvp-feature`, `mvp-enabler`, or `post-mvp`. Apply the `mvp` label if and only if it's one of the first two.
2. **New P1 default is OFF.** New work defaults to P2 unless explicitly tagged `mvp`.
3. **Enablers vs features** is the canonical lens — borrowed from foundation.md §§14–15. Schema slots and API seams that keep post-MVP features cheap belong in MVP; the user-facing features themselves usually don't.
4. **When in doubt, ask "does this block the launch definition?"** If not, it's post-MVP.

## Acceptance for MVP launch

The `tw-kdx1` epic closes when:

- Every `mvp`-labeled child ticket is closed.
- A trained operator runs one full operational period end-to-end on a fresh instance, including authentication, board work, CoT-IN, CoT-OUT, map use, realtime updates, and a successful backup/restore round-trip.
- This document and `tw-kdx1` agree on the final cut list.
