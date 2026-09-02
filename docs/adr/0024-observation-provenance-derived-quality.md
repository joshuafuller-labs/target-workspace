# ADR 0024 — Observation provenance and derived geometry quality

**Status:** Accepted
**Date:** 2026-06-03

## Context

The observation substrate is real and well-built. `TrackObservationTable` is an append-only, indexed, per-observation log; track-correlation (`db/track_correlation.py`) merges re-observations of one physical contact into a single persistent `Target` instead of spawning duplicates; and `api/confidence_fusion.py` (`tw-a9a`) fuses independent confidences with the correct independence rule, `aggregate = 1 − ∏(1 − cᵢ)`. This is a genuine `Target ← many Observations` model, and it is the substrate the ADR 0021 `ObservationFused` signal and `conditional` promotion policy are built to consume.

Verifying it surfaced two defects — one of them a safety defect.

**1. `geometry_quality` is disconnected from the evidence that defines it.** The quality ladder `bearing-only < single-source < corroborated < confirmed` is doctrinally load-bearing. The code's own comment on `GeometryQuality` says *"RoE matrices key off this explicitly: kinetic effectors typically require ≥ corroborated"* and *"workflow gates use it as a minimum quality precondition."* Yet the field:

- defaults to `"single-source"` (`db/tables.py`, `api/schemas.py`),
- is only ever set from the create body or demo YAML (`api/routers/targets.py`, `demo/loader.py`),
- and is **never promoted by `append_observation`**. A target can accumulate three *independent* observations, fuse to 0.95 confidence, and still report `geometry_quality = single-source` — even though "corroborated" is *literally defined* as "≥2 independent sensors agree."

So the field that RoE matrices and `conditional` autonomy gate on does not reflect the corroboration that actually exists. In a targeting context that is the dangerous failure mode: a gate that *looks* like it enforces corroboration is keyed to a hand-set string that never corroborates itself. This must be fixed before any quality-gated autonomy (ADR 0021's `conditional` mode) can be trusted.

**2. Provenance has two sources of truth, and the authoritative one isn't the immutable one.** Fusion writes and reads `target.custom_fields.confidence_chain` — a *mutable, operator-`PATCH`able, unsigned* JSON mirror — rather than the immutable `TrackObservationTable`. The append-only evidence exists but is not what drives the fused number. The two can drift, and the value feeding autonomy lives in the editable blob.

## Decision

### 1. `geometry_quality` is derived from the substrate, not stored as authoritative input

Quality is **computed** from the observations on each `append_observation`, not hand-set and frozen:

- count **independent** sources among the target's observations (independence keyed on source identity — see §4);
- 0–1 independent source → `single-source` (or `bearing-only` when the geometry is a line-of-bearing with no range);
- ≥2 independent sources → `corroborated`;
- `confirmed` is **not** a pure count — it additionally requires ID + position + classification locked, so it is asserted via an explicit signal/observation flag, never inferred from quantity alone.

The derived value is what RoE matrices and the `conditional` promotion policy read. Recompute is part of the observation-append path, so quality tracks evidence in real time.

### 2. Manual override is allowed but distinct, visible, and audited

An operator may still pin a quality (e.g., downgrade a noisy auto-`corroborated`). The override is stored in a **separate field**, visibly flagged in the UI as an override, and written as an audit event. The derived value remains computable underneath. Gates read the override when present, the derived value otherwise — and the fact that a human overrode the evidence is itself part of the record.

### 3. `TrackObservationTable` is the single source of truth for fusion

`fuse()` derives from the observation rows, not from `custom_fields`. `confidence_chain` becomes a **read-only projection** computed from the immutable log on read, and the mutable mirror is removed from `custom_fields`. Provenance — "which source said what, when, at what confidence" — is answered from the append-only table, the same table the audit chain (ADR 0023) and the `ObservationFused` signal reference.

### 4. Independence is the operator's cited assumption — carried, not hidden

The independence rule is only valid for genuinely independent cues; two observations from the same sensor, analyst, or upstream feed are correlated, and fusing them is wrong-optimistic. Each observation already carries its `source`. The derivation treats same-`source` observations as **one** independent cue, and the per-source breakdown is surfaced (in the projection) so an operator can see *why* a target is `corroborated`. Correlated-source inflation is a **curation** concern made visible, not silently fused away — consistent with `confidence_fusion.py`'s own honest docstring.

### Concrete rules

- **`geometry_quality` is derived, recomputed on every `append_observation`.** It is never a silently-trusted free input.
- **`confirmed` requires explicit ID+position+classification lock**, not a source count.
- **Manual override is a distinct, flagged, audited field** — it does not overwrite the derived value.
- **Fusion and provenance read `TrackObservationTable`**, the immutable log. `confidence_chain` is a projection, removed from mutable `custom_fields`.
- **Same-`source` observations count as one independent cue** for both fusion and quality derivation.
- **Derivation is correlation-bound and fails *closed* for geometry it cannot corroborate.** Track correlation is point-only today, so ellipse/polygon targets accumulate no correlated observations and **must not auto-promote past their seeded quality**. The derivation never invents corroboration it cannot substantiate: a quality gate on a non-point target therefore requires the *manual, flagged* corroboration override or stays blocked — it fails closed, never open — until non-point correlation (`tw-k4kg.14`) lands.

## Alternatives considered

- **A — Keep `geometry_quality` hand-set (status quo).** Rejected: the gate lies; corroboration the system *has* is invisible to the policy that requires it.
- **B — Derive quality but keep `confidence_chain` in `custom_fields`.** Rejected: leaves two sources of truth, one of them operator-mutable, driving autonomy.
- **C — Build a full provenance graph / formal ontology now.** Rejected: over-scoped. The `Target ← Observations` table answers the provenance questions we have; a graph is a later concern if multi-entity relationships demand it, and ontology lock-in is explicitly a pattern to avoid (research synthesis).
- **D — Derive quality + `TrackObservationTable` as single source of truth (this ADR).** Chosen.

## Consequences

**Wins:**
- RoE and `conditional`-policy gates key off **real, current evidence** — the central safety fix. The corroboration the system has is the corroboration the gate sees.
- Provenance is immutable and queryable from one append-only table, reinforcing (and reinforced by) the ADR 0023 audit chain.
- The `ObservationFused` signal (ADR 0021) now has a trustworthy substrate to carry: fused confidence and derived quality both trace to immutable rows.
- Removes an operator-mutable field from the autonomy decision path.

**Trade-offs accepted:**
- **"Independent source" detection is heuristic** — keyed on the `source` string today. Two distinct feeds that secretly share an upstream still read as independent. **Mitigation:** surface the per-source breakdown so a human can catch it; refine source-identity modeling later. We make the assumption *visible*, not correct-by-magic.
- **Coverage limitation:** derivation corroborates only *point* targets until ellipse/polygon correlation ships. For DF ellipses — where the ladder matters *most* (a single-collector ellipse vs tri-sensor fusion) — quality stays conservative (seeded value + manual override only) rather than falsely corroborating. Because this is a safety-coverage hole and not a mere enhancement, **`tw-k4kg.14` (non-point correlation) is raised from P3 to P2.**
- **Migration:** backfill `geometry_quality` by deriving from existing observations; migrate any `custom_fields.confidence_chain` into the projection and drop the stored copy. Targets created without observation rows fall back to their stored value as a single-source seed.
- Recompute on append adds a small cost to the hot ingest path. **Mitigation:** it's an O(observations-per-target) pass, bounded by correlation; batch where the source is high-rate (ETL posture).

## References

- [ADR 0021 — Workflow decision pipeline](0021-workflow-decision-pipeline.md) — `ObservationFused` signal and `conditional` policy consume the derived quality + fused confidence
- [ADR 0023 — Tamper-evident audit chain](0023-tamper-evident-audit-chain.md) — same immutable-log philosophy; provenance and audit reinforce each other
- [ADR 0008 — Malleability](0008-malleability-principle.md) — why a formal ontology is out of scope
- `src/target_workspace/db/track_correlation.py` — `append_observation` gains quality derivation; stops writing the mutable chain
- `src/target_workspace/api/confidence_fusion.py` (`tw-a9a`) — `fuse()` sources from `TrackObservationTable`
- `src/target_workspace/models/target.py` — `GeometryQuality` ladder; gains a distinct override field
- `docs/research/ukraine-fires-targeting.md` §5 — why DF-ellipse quality and corroboration drive RoE
- Implementation: `tw-k4kg.9` (derive quality), `tw-k4kg.10` (fusion single-source-of-truth), `tw-k4kg.14` (correlation un-merge) — all gated by this ADR
