# ADR 0026 — Federation conflict/merge model

**Status:** Accepted
**Date:** 2026-06-03

## Context

Federation is designed at the transport level — ADR 0015 (multi-org groups in a workspace), ADR 0016 (federation transport as a separate plane), ADR 0020 (tw_mesh), and `tw-g21g` (peer CRUD + `/v1/federation/inbox` + send queue). What is **not** decided is what happens when two peers edit the same thing while partitioned.

This is not an edge case in our domain. TAK operates in DDIL conditions — disconnected, intermittent, low-bandwidth — by default. Partitions are the normal mode, not the exception. Two cells sharing a target (ADR 0017 gives targets a stable cross-instance identity via their CoT UID) will routinely edit it out of contact and reconnect later. `Target.version` is monotonic *per instance*, which is fine for single-writer offline-then-sync but provides **no merge rule** when two writers diverge: you get two version-5s with different contents and no defined winner.

Pick the merge model wrong and you get one of two failures: silent data loss (a blind overwrite drops a concurrent edit) or — far worse in this domain — a blind overwrite that **silently reverts a human workflow decision** (peer B's stale "Investigate" clobbers peer A's deliberate "Cleared").

## Decision

A **per-field, causally-ordered merge** with three carve-outs that match the data's nature.

### 1. Identity is agreed; only values conflict

Targets share a stable identity — the CoT UID (ADR 0017, and the feed-native-UID rule). Peers never disagree about *what* a target is, only about field values and workflow column. That bounds the problem to per-field reconciliation.

### 2. Per-field last-writer-wins by hybrid logical clock

Replace the bare monotonic `version` with a per-field update stamp: a **hybrid logical clock** `(hlc, peer_id)`. Merge is per-field `max` by `(hlc, peer_id)` tiebreak — CRDT last-writer-wins *register* semantics, applied field-by-field. This is deterministic, commutative, and convergent: any two peers applying the same set of updates in any order reach the same state. The HLC's logical component absorbs wall-clock skew across peers, so we do not depend on synchronized clocks (which DDIL cannot guarantee).

### 3. Workflow column conflicts escalate to a human — never blind-LWW

The board column is special: it encodes a deliberate human (or policy) decision, and silently LWW-ing it can undo one. So when two peers moved the same card to **different** columns while partitioned, the merge does **not** pick a winner — it raises a `Nomination` (ADR 0021) carrying both proposed states and their causal stamps, and a human resolves it. This is the same philosophy as ADR 0021's conflicting-destination rule: when autonomy is not confident, ask a human.

### 4. Observations union-merge; quality recomputes

Observations are append-only (ADR 0024). Two peers' observation sets simply **union** — there is no conflict, because nothing is overwritten. After merge, fused confidence and derived `geometry_quality` recompute from the unioned set. This is the easy, correct case, and it is *why the Target ← Observations split matters*: the highest-volume federation traffic (sensor hits) merges trivially and correctly.

### 5. Audit chains do not merge

Each peer keeps its own per-`(workspace, peer)` hash-linked audit chain (ADR 0023) intact — chains are never interleaved or rewritten. A merge writes its **own** audit event on the local chain, citing the remote causal stamps it reconciled (what was overwritten, by whose stamp, when). Cross-peer ordering, when needed, comes from the signed Merkle checkpoints reserved in ADR 0023.

### Concrete rules

- **Stable identity** via CoT UID (ADR 0017); merge reconciles values, not identity.
- **Per-field LWW by `(hlc, peer_id)`** — deterministic, commutative, convergent; HLC absorbs clock skew.
- **Workflow-column conflicts raise a `Nomination`** — never blind-LWW a human decision.
- **Observations union-merge; confidence + quality recompute** from the union.
- **Audit chains stay per-peer**; a merge is itself an audited event citing remote stamps; cross-peer order via checkpoints.
- **Every merge decision is audited.**
- **This model supersedes the bare monotonic `version`** sketched as the offline-sync placeholder in ADR 0012 and used in ADR 0017: `version` becomes the HLC seed, and any etag-style optimistic concurrency keyed on a single integer moves to per-field stamps. Under per-peer audit chains (ADR 0023), ADR 0017's "unified audit timeline per `target_id`" is a cross-peer *logical merge* view, not a single physical chain.

## Alternatives considered

- **A — Blind whole-record last-write-wins.** Rejected: drops concurrent edits and can silently revert human workflow transitions — the worst failure in this domain.
- **B — Full CRDT document (Automerge / Yjs) over the whole Target.** Rejected: heavyweight, opaque to the audit story, and overkill for fields that are mostly simple LWW registers; fights ADR 0008's single-container simplicity.
- **C — Operator resolves every conflict.** Rejected: does not scale under frequent DDIL partitions and defeats the point of autonomy; humans should adjudicate only what genuinely needs them (workflow).
- **D — Per-field HLC-LWW + escalate workflow conflicts + union observations (this ADR).** Chosen: CRDT-correct where it is cheap (registers, append-only sets), human-in-the-loop only where a wrong merge would erase intent.

## Consequences

**Wins:**
- Deterministic convergence after any partition pattern — the core requirement.
- The one dangerous case (divergent workflow state) gets a human via the existing `Nomination` machinery; no silent reversion of a decision.
- The high-volume path (observations) merges trivially and recomputes correctly — the observation split pays off again.
- Audit integrity is preserved per-peer; merges are themselves auditable.

**Trade-offs accepted:**
- HLC adds a per-field (or compact per-target field-stamp map) clock. **Mitigation:** stamps are small; group rarely-conflicting fields.
- Convergence assumes agreed identity (ADR 0017). A mis-correlated UID across peers would merge two distinct contacts — a correlation/curation problem (ADR 0024 #2c, un-merge), not a merge-algorithm problem.
- **Migration:** introduce HLC stamps seeded from the existing monotonic `version`; pre-federation single-writer history is unaffected.

## References

- [ADR 0015 — Multi-org groups in a workspace](0015-multi-org-groups-in-workspace.md), [ADR 0016 — Federation transport plane](0016-federation-transport-separate-plane.md), [ADR 0020 — tw_mesh federation](0020-tw-mesh-federation.md) — the transport this merge sits on
- [ADR 0017 — Cross-board targets, shared identity](0017-cross-board-targets-shared-identity.md) — the stable CoT-UID identity merge relies on
- [ADR 0021 — Workflow decision pipeline](0021-workflow-decision-pipeline.md) — `Nomination` resolves workflow-column conflicts; conflicting-destination philosophy
- [ADR 0023 — Tamper-evident audit chain](0023-tamper-evident-audit-chain.md) — per-peer chains + Merkle checkpoints for cross-peer ordering
- [ADR 0024 — Observation provenance & derived quality](0024-observation-provenance-derived-quality.md) — observations union-merge; quality recomputes post-merge
- Implementation: `tw-k4kg.13` (gated by this ADR), extends `tw-g21g` transport
