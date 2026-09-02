# ADR 0017 — Cross-board target model: shared identity + per-board state

Status: Accepted (ratified 2026-06-03).

> **Ratified 2026-06-03** alongside the federation work that depends on it (ADR 0026). The shared-identity + per-board-state model and the CoT-UID addressing are confirmed. Note: ADR 0026 supersedes the bare monotonic-`version` mechanism referenced here with per-field hybrid-logical-clock stamps, and under per-peer audit chains (ADR 0023) the "unified audit timeline per `target_id`" becomes a cross-peer *logical merge* view rather than a single physical chain.

## Context

`tw-n0b4` sharpened the scope of `tw-v8s` (cross-board target linking + Send-to-board action). The original `tw-v8s` description used a "linked_target_id relation + Send-to-board moves primary home + leaves stub on original" model. That model has two problems:

1. It bifurcates the audit chain (each linked record has its own history).
2. It can't represent independent column-positions per board (SAR FOUND vs Medical TRIAGE for the same person at the same instant).
3. It has no relationship to the cross-instance transfer case (federation Send-to-peer).

## Decision

**Shared identity + per-board state.** One canonical target row, plus a `target_board_link` join table:

- `target_board_link(target_id, board_id, column_id, position, added_at, added_by, removed_at, status)`
- A target appears on a board iff a non-tombstoned link exists.
- `column_id` + `position` are per-board (independent workflow state per board view).
- Updates to canonical fields (name, lat/lon, attachments) propagate across all views automatically because there is only one record.
- Audit chain is unified per `target_id` (events carry `board_id` for context but the timeline is one query).

Send-to-board action:
- "Add to board X" = INSERT a non-tombstoned link.
- "Remove from board X" = soft-delete the link (`removed_at`).
- "Transfer ownership" is a no-op at the data layer — there is no privileged "home board"; just links.

Send-to-peer (federation case):
- Local Send-to is the degenerate form: destination is a local `board_id`.
- Federation Send-to: destination is a peer's board addressable as `did:tw:<peer-id>:board:<id>`.
- Sender packages target + audit slice + signed provenance (per ADR 0016 / `tw-16c0`); POSTs to peer `/v1/federation/inbox`.
- Sender's instance does not forget — `target.transferred_to_peer_id` + timestamp; local copy becomes read-only "transferred" state.

Seven specific design questions resolved:

1. **target_board_link vs separate target_board_state table** — target_board_link only; per-board state lives in the link row.
2. **Home-board concept** — none. UX may surface "originating link" but it's not privileged.
3. **Tombstones vs hard delete** — soft-delete on the link (`removed_at`). Hard delete only via admin debug tool, recorded.
4. **Idempotency keys for cross-instance Send-to** — sender includes a `transfer_id`; receiver upserts by `(sender_peer_id, transfer_id)`.
5. **Receiver dedup policy** — surface fuzzy-match candidates as "possible duplicate" suggestions; require human merge. No automatic dedup.
6. **Addressing scheme** — `did:tw:<peer-id>:board:<id>` and `did:tw:<peer-id>:target:<id>`. Local case omits the peer-id segment (`did:tw::board:<id>`).
7. **Orphan handling on last-link-removed** — target archives (still queryable; not on any board). Hard delete is separate.

## Consequences

- `tw-v8s` description should be updated to reference this ADR and the above model.
- Schema migration ships at MVP per `tw-v8s` reverted P2→P1 scoping (schema only; UX deferred).
- `tw-icj8` workspace groups proceed independently — `board.owning_group_id` and group membership ACL compose with this model cleanly (board ACL ladder gates whose links are visible).
- The Send-to UX (post-MVP) presents one menu including local-board destinations AND known-peer-board destinations once federation lands. The UX layer hides the local/remote distinction; the underlying call is `POST /v1/targets/{id}/links` vs `POST /v1/federation/outbox`.

## Status note

This ADR was authored autonomously during the 2026-05-18 `/goal` session per the directive to make a conservative engineering assumption when the user is unavailable. Flagged for explicit user sign-off on next session.
