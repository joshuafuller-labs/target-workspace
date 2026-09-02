# ADR 0025 — A CoT `<detail>` extension for detection metadata

**Status:** Accepted
**Date:** 2026-06-03

## Context

The prior-art research (`docs/research/05-ai-cv-to-cot.md`, `SYNTHESIS.md`) surfaced a concrete, time-sensitive standards gap. MITRE's CoT Sensor Schema covers sensor *pointing* — azimuth, FOV, range, model, version — but has **no confidence field, no bounding box, no detection metadata** of any kind. So every vendor producing AI/ATR detections (Planet, BlackSky, YOLO pipelines, Anduril, Maven) rolls its own `<detail>` payload, and confidence scores aren't comparable across them. There is no portable way for an AI detection to travel through CoT carrying *how sure* it is, *what model* produced it, and *where it came from*.

This matters to us specifically because we are CoT-native and we *produce exactly this metadata*: fused confidence and the derived `geometry_quality` ladder (ADR 0024), the per-source provenance chain, and (via ADR 0021) the principal and attestation behind every state change. When we publish a target to ATAK or any CoT consumer, that metadata currently has nowhere standard to go.

Two strategic facts make this a now-decision, not a someday-decision:

1. **First mover defines the standard.** Whoever publishes a credible, open `<detail>` schema for detection metadata shapes how AI detections move through CoT across the whole ecosystem.
2. **The window can close.** If the TAK Coalition / TPC standardizes detection metadata before we ship a reference, we lose the shaping opportunity (a named risk in the synthesis).

snstac's `*2cot` tools laid real groundwork for AI/sensor data into CoT. We build on and credit that work — never frame it as competition (it is the foundation this sits on).

## Decision

Define, publish, and ship a **reference implementation** of a CoT `<detail>` sub-schema for detection metadata.

### 1. Extend `<detail>`, do not fork the type tree

The detection metadata lives in a namespaced child of `<detail>` (e.g. a `<detection>` element), **not** in new CoT `a-*` type-tree entries. Forking the CoT type taxonomy is an explicit anti-pattern (research: "the standard exists; extend the `<detail>` payload"). The element carries:

- `confidence` (0..1) — with a *declared semantic* (see §2)
- `geometry_quality` — the ADR 0024 ladder (`bearing-only`/`single-source`/`corroborated`/`confirmed`)
- `bbox` (optional) — detection bounding box in the sensor frame
- `model` — `{ id, version }` of the producing model/pipeline
- `provenance` — source feed / observation reference (ties to the ADR 0024 substrate)
- `observed_at` — source-detection time (distinct from CoT event time)
- `schema_version` — for evolution without breaking old parsers

### 2. Confidence is portable by *declaration*, not by pretending comparability

Cross-vendor confidence scores are genuinely not comparable (a Planet score and a YOLO score don't mean the same thing). We do not paper over that. Instead the schema **declares its semantic**: our `confidence` is the independence-rule aggregate defined in ADR 0024, and the element names that. A consumer then knows what `0.95` means here, rather than silently mixing incomparable numbers. Other producers declaring their own semantic is exactly the interop the standard should enable.

Critically, the element carries **both the aggregate and its inputs**: a `sources[]` array of `{source, confidence, observed_at}` alongside the named aggregation method. Because independence is a heuristic assumption (ADR 0024 keys it on the `source` string, and same-upstream feeds can read as independent), a consumer must be able to *re-judge* — so the per-source breakdown is **mandatory, not optional**, and the bare aggregate is never published alone.

### 3. Ship the reference impl regardless of blessing

We implement the schema in our CoT-in / CoT-out plugins (`tw-k4kg.12`) as the reference (de)serializer **immediately**, so our value does not depend on a committee. In parallel we publish the schema openly, credit snstac's prior art, and take it to the TAK Coalition / TPC for blessing — with a standing standards-watch note tracking competing activity (research recommendation).

### Concrete rules

- **Extend `<detail>`; never fork the CoT `a-*` type tree.**
- **`confidence` carries a declared semantic** (ADR 0024 aggregate); no silent cross-vendor mixing.
- **The schema is versioned** (`schema_version`) and published under an open license.
- **Credit snstac / `*2cot`** as prior art in the schema and docs.
- **Reference impl ships independent of Coalition blessing**; we are never blocked on a standards body.

## Alternatives considered

- **A — Keep a private `<detail>` payload (status quo for everyone).** Rejected: misses the standards-shaping moat and the interop win; perpetuates the every-vendor-rolls-their-own mess.
- **B — Wait for the TAK Coalition to define it.** Rejected: cedes first-mover and the shaping opportunity; the synthesis flags this exact risk.
- **C — Add detection types to the CoT type tree.** Rejected explicitly — forking the taxonomy is an anti-pattern; the type tree is not ours to extend.
- **D — Publish a `<detail>` extension + reference impl + pursue blessing (this ADR).** Chosen.

## Consequences

**Wins:**
- A credible shot at owning the de-facto standard for AI-detection-over-CoT — a standards moat that compounds adoption.
- Real interoperability: our targets carry their confidence/quality/provenance to ATAK and any CoT consumer in a documented, parseable form.
- Open-source credibility from contributing a schema upward (and crediting prior art), consistent with the community-first posture.

**Trade-offs accepted:**
- Standards work is slow and political. **Mitigation:** the reference impl ships regardless; blessing is upside, not a dependency.
- The Coalition may diverge from our schema. **Mitigation:** `schema_version` + a thin adapter let us converge later without breaking shipped data.
- We must maintain the schema as a public artifact. Accepted — it is the point.

## References

- `docs/research/05-ai-cv-to-cot.md`, `docs/research/SYNTHESIS.md` — the CoT detection-metadata gap; MITRE Sensor Schema; first-mover/standards-watch risk
- [ADR 0024 — Observation provenance & derived quality](0024-observation-provenance-derived-quality.md) — the confidence semantic and `geometry_quality` ladder this schema carries
- [ADR 0021 — Workflow decision pipeline](0021-workflow-decision-pipeline.md) — principal/attestation context that can ride alongside detection metadata
- snstac `*2cot` tools (`aircot`/`adsbcot`/`aiscot`) — prior art this builds on and credits
- Anduril Lattice Entity API — component-model semantics worth mirroring at the edge
- Implementation: `tw-k4kg.12` (gated by this ADR)
