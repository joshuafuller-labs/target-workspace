# ADR 0020 — tw_mesh federation: tiered access, wire protocol, conflict resolution

Status: Accepted (provisional — flagged for user review).

> Note on numbering: the original `tw-ujh` ticket targeted "ADR 0015" but `0015` is taken by multi-org-groups-in-workspace. Federation transport already lives at ADR 0016. This ADR is the *deeper* federation companion that ADR 0016 deferred — tiered access, wire protocol choice, event shape, conflict resolution, threat model, and failure semantics.

## Context

ADR 0016 picked the high-level *plane*: federation control + data lives on its own HTTPS-fronted plane, distinct from CoT-IN / CoT-OUT operational traffic.

The follow-up open questions:

- **Tiered access**. Disaster-ops / military scenarios are inherently hierarchical (battalion → brigade → division; field team → ICS branch → unified command; local PD → mutual-aid → state EOC). The peer model needs to encode that without forcing every instance to know every peer.
- **Wire protocol**. Three plausible choices: gRPC over mTLS, signed HTTPS pull (peer-initiated), or NATS / message-bus style fan-out. Each has different operational shapes.
- **Event envelope**. Does the federation slice carry the same JSON shape as the in-process realtime broker emits, or does it need its own framing?
- **Conflict resolution**. Two peers edit the same canonical target row independently — which wins?
- **Threat model**. Authenticated peer is the smallest unit of trust. What does "trust" actually grant?
- **Failure semantics**. Federation must NEVER block local operations — what happens when peers are unreachable?

## Decisions

### 1. Tiered access

**Each instance keeps a list of authorized peers, full stop. No transitive trust.**

If instance A trusts B, and B trusts C, A does NOT thereby trust C. The transitive case is solved by explicitly federating A↔C if that's desired.

Rationale: the alternative (PKI hierarchies with chain-of-trust) is operationally brittle in disaster scenarios where peers come and go on hours-notice. Flat lists of explicit pair-trust scale just fine into the dozens-of-peers range that real incidents reach. Above that, peers organize by *role* (every county EOC connects to the state EOC, not to every other county) which keeps the mesh sparse without policy invention.

The peer list is workspace-scoped and admin-managed. Each peer entry carries:

- `peer_id` (UUID, namespaced as `did:tw:<peer-id>`)
- `display_name` (operator-facing label)
- `public_key_pem` (the peer's ed25519 identity per `tw-16c0`)
- `inbound_url` (where we POST federation slices for this peer)
- `share_policy` (which boards / groups this peer can see; default: explicit allowlist)

### 2. Wire protocol

**Signed HTTPS push. JSON over `POST /v1/federation/inbox`. mTLS-optional.**

Rejected alternatives:

- **gRPC + mTLS** — adds a binary stack and a separate port. mTLS is genuinely useful, but as the *only* auth mechanism it's painful to provision in a disaster scenario where peers may use self-managed certs. We make mTLS an *optional* extra layer; primary auth is the per-event ed25519 signature from `tw-16c0`.
- **NATS / message-bus fan-out** — would require a broker on the path, defeating the point of a peer-to-peer mesh. Reserved for the (post-MVP) "regional concentrator" pattern.

Push (not pull) because:

- Audit events are append-only; the sender knows their state, the receiver doesn't need to poll.
- Receivers that are offline get a queue-then-retry pattern; senders re-send when peers come back online.
- HTTP idempotency (per-event UUIDs) makes duplicate POSTs harmless.

### 3. Event envelope

**Re-use the realtime broker event envelope; wrap with a federation header.**

```json
{
  "fed": {
    "from_peer_id": "did:tw:<uuid>",
    "ts": "2026-05-18T14:32:00Z",
    "signature": "<ed25519 sig over inner event>",
    "envelope_version": 1
  },
  "event": { /* identical to /v1/subscribe event */ }
}
```

This means the *same code path* that fans realtime events to WebSocket clients also handles federation receipt — receiver de-envelopes, verifies signature against the sender's `public_key_pem`, then injects into its own audit log + realtime broker. No second event schema to keep in sync.

### 4. Conflict resolution

**Append-only on audit. Last-writer-wins on metadata, scoped to the workspace that owns the row.**

The canonical target row has a single home workspace. Edits to fields like `name`, `lat`, `lon`, `confidence` are last-writer-wins by `(updated_at, peer_id)` tuple — newest wins; tie broken by peer_id lex order.

Audit events are *append-only* by definition, so there's no conflict — both peers' events land in both peers' audit logs, signed by their authors, ordered by `occurred_at`. The "merged" timeline is one query per `target_id`.

`assigned_callsigns` (which has receive-side semantics — "I'm tracking this card from my agency") is union-merge across peers. Each peer locally sees the union; the home workspace sees who claimed it from where.

### 5. Threat model

**Authenticated peer = "I trust this peer to make claims about its own state."**

It does NOT mean:

- "I trust this peer to assert facts about a third peer." (Hence no transitive trust.)
- "I trust this peer's audit chain as authoritative." (We verify their signature; we add our own when we re-publish.)
- "I trust this peer to bypass our local RBAC." (Federation receipts still pass through our normal RBAC + workflow gates — a federated `target.created` lands as if a Source plugin emitted it locally; gated columns still gate, approval roles still apply.)

Compromised-peer recovery: an admin can revoke a peer at any time (`DELETE /v1/federation/peers/{peer_id}`); the receiver-side verification then rejects every subsequent event from that peer. Historical events stay in the audit log (they're already signed, append-only) but are visually flagged.

### 6. Failure semantics

**Federation is best-effort. Local operations NEVER block on a peer being reachable.**

- Outbound send queue is bounded; drops the oldest when full and emits a `federation.send.queue_overflow` audit event so an operator can investigate.
- Per-peer circuit breaker — three consecutive HTTPS failures opens the breaker for 60s, with exponential backoff to a 1-hour cap.
- Local kanban + map + workflow engine never check peer reachability; they always operate against the local DB.

## Consequences

- Concrete implementation lands in `tw-0xg` (deferred per MVP grooming).
- The signed-audit feature (`tw-16c0`) is now *load-bearing* for federation; preserving the per-instance keypair + per-event signature is non-negotiable.
- Federation introduces a new bd cluster — peer CRUD endpoints, inbox endpoint, send queue, circuit breaker, share-policy admin UI.
- ADR 0018 attachment storage already aligns: hash-list-then-pull means attachments don't bloat federation slices.

## Status note

Authored autonomously during the 2026-05-18 `/goal` session per the directive to make a conservative engineering assumption when the user is unavailable. Flagged for explicit user sign-off on next session.
