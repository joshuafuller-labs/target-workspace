# ADR 0015 — Multi-org model: groups-in-workspace

Status: Accepted (provisional — flagged for user review).

## Context

The 2026-05-18 Helene-shape conversation raised the question of whether sub-organizations (Cajun Navy, Mission Hospital, Tennessee USAR strike team) coexist on one Target Workspace instance or each runs their own.

- **Option A — Groups-in-workspace.** One workspace per instance; many sub-org groups inside. Schema: `group` + `group_member` tables, `board.owning_group_id` foreign key, ACL ladder includes group check. Federation only matters between major-peer instances (FEMA HQ ↔ Buncombe EOC ↔ SC State EM) — 5–10 peer relationships, tractable.
- **Option B — Full multi-tenancy.** Many workspaces per instance; every endpoint becomes tenant-scoped (`workspace_id` on every table; tenant header / subdomain routing; auth scoped per tenant). Blast radius: every endpoint, every test, every query. Foundation §17 explicitly says "Multi-tenancy | Out of MVP".

`tw-eo6l` ticket is the explicit gate on `tw-icj8` (workspace groups schema), `tw-liwf` (per-resource ACL), `tw-v8s` (cross-board target linking), and any work that touches the multi-tenancy axis.

## Decision

**Option A, groups-in-workspace.**

Rationale:

- Foundation §17 already ruled out multi-tenancy for MVP. This decision affirms that ruling and adopts the lighter pattern that achieves the same operational shape.
- Helene reality: sub-orgs sharing one instance + per-resource ACL is operationally sufficient. Cross-instance federation between major orgs handles the rest.
- Multi-tenancy proper is a months-of-effort architectural commitment. Single PM building this; not justified pre-pilot.
- Lighter pattern is composable forward: if `Workspace` becomes the multi-tenant boundary later, today's `Group` becomes the sub-org abstraction inside it without schema churn.

## Consequences

- `tw-icj8` workspace groups can proceed: `group`, `group_member`, `board.owning_group_id`, ACL ladder.
- `tw-liwf` per-resource ACL data-model hooks proceed: `board_acl`, `target_acl`, check ladder (target > board > group > workspace).
- `tw-v8s` cross-board target linking proceeds with the assumption that "another board" is always local-instance for MVP (cross-instance Send-to-peer is gated by `tw-a3ix` federation transport).
- Per-tenant branding / per-workspace settings (`tw-smc`, `tw-el5q`) stay as workspace-level concerns; no tenant abstraction sits above them.

## Status note

This ADR was authored autonomously during the 2026-05-18 `/goal` session per the directive to make a conservative engineering assumption when the user is unavailable. Flagged for explicit user sign-off on next session.
