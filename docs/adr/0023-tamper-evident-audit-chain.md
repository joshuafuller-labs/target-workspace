# ADR 0023 — Tamper-evident audit: a hash-linked, signed log

**Status:** Accepted
**Date:** 2026-06-03

## Context

The signed audit log is the product's load-bearing differentiator. The pitch — repeated across the README, the research synthesis, and the LE/DoD go-to-market — is that *"chain-of-custody and FOIA response are queries, not reconstructions."* ADR 0021 leans on it harder still: typed `Principal`s, `Nomination` records, and denied-move events all derive their trustworthiness from the audit log being honest.

Today it is not honest enough to back that claim. The implementation (`tw-16c0`, `api/signing.py`, 149 lines) does two correct things and is missing a third:

1. **Each event is individually signed** — a per-instance ed25519 keypair signs the event's content at insertion (`peer_id` + `signature` columns).
2. **The table is append-only** — `models/audit_event.py` enforces no `UPDATE` / `DELETE` *at the persistence layer*.
3. **But events are not linked to each other.** There is no `prev_hash`, no sequence binding, nothing that ties event N to event N−1.

The consequence is concrete and disqualifying for the claim: a party with database access can **selectively delete or reorder** events and the remaining signatures still verify. "Append-only" is an application convention enforced by code we ship, not a property an auditor can independently confirm against a motivated insider. Individual signatures prove *"this row was authored by this instance"*; they do not prove *"these are all the rows, in this order, with none removed."* Chain-of-custody — and FOIA/CJIS/court defensibility — requires the second property. That is the gap this ADR closes.

## Decision

Make the audit log a **hash-linked, signed chain** — a verifiable log, the same shape transparency logs and tamper-evident ledgers use.

### 1. Each event links to its predecessor

Every audit event gains a `prev_hash`. On insertion:

```
event_hash = SHA-256( canonical(event_content) || prev_hash )
signature  = ed25519_sign( peer_key, event_hash )
```

- `canonical(event_content)` is a deterministic serialization (sorted keys, fixed encoding) of the signed fields — actor, event_type, target, occurred_at, from/to column, justification, metadata. **The actor is whatever the schema holds at write time**: a bare `actor_id` UUID in the pre-pipeline schema, the typed `Principal` (ADR 0021) once it lands. Because this ADR's implementation (`tw-k4kg.8`) *precedes* the pipeline refactor (`tw-k4kg.7`), the v1 chain signs `actor_id`; when `Principal` arrives, `format_version` increments and `verify` validates each segment against the format it was written under. The hash construction itself does not depend on which actor representation is current.
- **`prev_hash` is inside the signed content.** The link itself is signed, so an attacker cannot re-link a forged predecessor without the key.
- `event_hash`, `prev_hash`, `signature`, and `peer_id` are persisted alongside the existing fields.

### 2. The chain is per `(workspace, peer_id)`

Each instance (peer) maintains its own chain head per workspace. This matches the federation design — federation reuses the signature path (`tw-16c0`), and each peer signs its own events with its own key. Cross-peer total ordering is **not** attempted here; it is deferred to checkpoints (below). The genesis link is a fixed sentinel hash recorded when a workspace's chain starts.

### 3. Verification is a first-class endpoint

`GET /v1/audit/verify` (scoped to a workspace, optionally a peer) walks the chain and returns either `ok` or the **first break**: the index, the expected vs actual `prev_hash`, and whether the failure is a broken link (deletion/reorder) or a bad signature (forgery/corruption). Verification recomputes each `event_hash`, checks the linkage, and verifies the signature against the peer's public key. This is what an auditor runs; it requires no trust in our application code.

### 4. Federation checkpoints are reserved, not built

For long logs and cross-peer trust, a peer may periodically publish a **signed Merkle checkpoint** (root over a range of `event_hash`es). This lets a federated peer attest "my log contained exactly these events as of time T" without shipping every row. The schema reserves room for it; the implementation is deferred until federation merge (ADR 0026) needs it.

### 5. Migration is honest about the pre-chain prefix

Existing rows were signed *without* covering a `prev_hash`. The migration backfills `prev_hash` over existing events in insertion order from the genesis sentinel and records a one-time **migration checkpoint** marking the boundary. `verify` reports everything before the checkpoint as a *"signed but pre-chain"* prefix — individually authentic, but not linkage-protected — and everything after as fully chained. We do not pretend retroactive tamper-evidence we cannot provide.

### Concrete rules

- **Every audit write computes and signs `prev_hash`.** No event enters the log unlinked (post-migration).
- **The link is inside the signature.** Signing covers `event_hash`, which covers `prev_hash`.
- **Hash is SHA-256; serialization is canonical and versioned.** A `hash_alg` / `format_version` field allows future rotation without breaking old verification.
- **Chains are per `(workspace, peer_id)`.** No cross-peer ordering assumption.
- **`verify` is independent of application trust** — it depends only on stored fields + the peer public key.
- **No silent truncation.** `verify` distinguishes a broken link from a bad signature from the pre-chain prefix.

## Alternatives considered

- **A — Status quo (per-row signatures only).** Rejected: proves authorship, not completeness or order; the differentiator's core claim fails against an insider.
- **B — External transparency log (Trillian / Sigstore Rekor / a blockchain).** Rejected: violates the single-container hobbyist default (ADR 0008 — runs on a Pi with one `docker run`), adds an external trust dependency and operational weight far beyond the problem. The verifiable-log *pattern* is right; the heavyweight *infrastructure* is not.
- **C — Periodic full snapshots only.** Rejected: coarse (gaps between snapshots are unprotected) and storage-heavy; a hash chain is continuous and cheap.
- **D — Hash-linked + signed chain (this ADR).** Chosen: continuous tamper-evidence, single-container-friendly, federation-ready via checkpoints.

## Consequences

**Wins:**
- The differentiator becomes *true*: deletion or reordering of any mid-chain event fails `verify`. Chain-of-custody is now a property an auditor confirms, not a promise we make.
- Strengthens every ADR 0021 construct (signed Principal attribution, Nominations, denied-move records) by making the log they live in tamper-evident.
- Federation gets a cheap cross-peer integrity primitive (checkpoints) for free from the same construction.
- Cost is small: one indexed column, one hash per insert, one verify endpoint.

**Trade-offs accepted:**
- The **pre-migration prefix is not retroactively linkage-protected** — it can't be; those signatures didn't cover a link. We mark the boundary honestly rather than overclaim.
- Audit inserts gain a serialize-and-hash step and must be **strictly ordered per chain** — the chain head is a serialization point, and the marquee PLI→workflow path (`tw-d3t9`) is deliberately high-rate, so this contention is real, not hypothetical. **Mitigation:** a single-writer **append queue per `(workspace, peer)` chain** — ingest enqueues and returns immediately; one serial committer assigns `prev_hash`, signs, and commits in order, decoupling ingest latency from chain serialization. Per-`(workspace, peer)` scoping bounds cross-instance contention, and **per-board sub-chains** are available if one workspace's write rate outgrows a single chain. High-rate sources should still batch (ETL posture).
- Canonical serialization must be pinned forever (or versioned). **Mitigation:** the `format_version` field.

## References

- [ADR 0021 — Workflow decision pipeline](0021-workflow-decision-pipeline.md) — `apply` writes the audit events this chain protects; typed `Principal` is the signed actor
- [ADR 0008 — Malleability / single-container default](0008-malleability-principle.md) — why an external transparency-log service is rejected
- [ADR 0026 — Federation conflict/merge](0026-federation-conflict-merge.md) — consumer of the checkpoint primitive
- `src/target_workspace/api/signing.py` — gains `prev_hash` linkage; signature covers the link
- `src/target_workspace/models/audit_event.py` — gains `prev_hash`, `event_hash`, `hash_alg`, `format_version`
- Prior work: `tw-16c0` (signed events + peer-id slot), `tw-4g6` / `tw-ixb` (append-only writer)
- Implementation: `tw-k4kg.8` (gated by this ADR)
- Pattern: Certificate Transparency / verifiable logs (RFC 6962, append-only Merkle); CJIS v6.0 audit requirements
