# Prior Art Synthesis

Distilled from five focused research reports covering the TAK ecosystem, commercial defense tech, doctrinal/process tooling, LE/public-safety analogues, and AI/CV-to-CoT pipelines. Each bucket's full report is alongside this file.

## Headline finding

**Kanban-for-targeting is not a novel concept. It is the operating pattern of Palantir's Maven Smart System "Target Workbench" — a workflow product Palantir markets to DoD with explicitly configurable, organization-tailored stages.** Maven hit ~20,000 users across 35 tools by early 2026, transitioned to a formal program of record in March 2026, and runs under a contract ceiling near $1.3B. Anduril Lattice fills the adjacent space at a $20B ceiling. Gotham anchors the analyst tier.

What does not exist anywhere we searched is a **CoT-native, source-pluggable, publisher-pluggable, affordable** version of this workflow. Across TAK.gov, OpenTAKServer, CivTAK, and the TAK Coalition community catalogs, no plugin or stand-alone product implements user-defined column workflow over CoT. The closest TAK-native primitive is ExCheck (locked checklists), and the closest stateful primitive is the Mission API (a flat event list with three subscriber roles, no transitions). Among large commercial platforms, only DroneShield treats CoT/TAK as a first-class output. Palantir, Anduril (in product), Helsing, Shield AI, Rebellion, and Onebrief either route CoT through partners or not at all.

That defines the wedge cleanly: **the workflow Maven sells to PEO C3T-tier customers, delivered CoT-first, plugin-driven, and accessible to coalition partners, allied militaries, federal LE, state/local public safety, SAR teams, and expeditionary units that will never sit on a Maven seat.**

## What each bucket told us

**TAK ecosystem.** Two SDKs are battle-tested and worth standing on: `pytak` (Python, async producer/consumer) and `node-cot` / `node-tak` (TypeScript, MIT). OpenTAKServer's Flask Blueprint plugin model — declared config, iframe UI surface — is the cleanest plugin-distribution pattern in the open ecosystem. The Mission API gives delta-sync and grouping but has no concept of state transitions; that's our opportunity. TAK-GPT's pattern of exposing a server-side plugin as a TAK contact is a zero-install UX win we should mirror. Distribution is fragmented between TAK.gov (click-through, attested) and community GitHub.

**Commercial defense-tech.** Maven Target Workbench validates the kanban thesis verbatim. Anduril Lattice's Entity API (assets, tracks, geo-entities, the `milView` component for disposition, StreamEntities for lifecycle) is the cleanest internal data model for evolving AI detections — better than CoT's rigid hyphenated type tree. The pattern across Maven and AIP is "AI proposes, human decides," with mandatory HITL gates for destructive action — this is now industry norm and reflects DoDD 3000.09. Pricing tiers are stratified: Maven at the top, Lattice for sensor fusion, Gotham (~$141K/core) for analyst tooling, and effectively nothing in the middle for the customers we want.

**Doctrinal/process tooling.** The kanban columns are not ours to invent. Doctrine gives us four ready-made templates: F3EAD (SOF/IC), D3A (Army FM 3-60, Aug 2023), Joint Targeting Cycle (JP 3-60, six phases), and F2T2EA (USAF kill chain). CJCSI 3370.01 codifies a five-target-type taxonomy — Facility, Individual, Virtual, Equipment, Organization — which is the natural ontology our `Target` object should adopt. Existing programs of record (JTT, GCCS-J, DCGS) are stovepiped by service and slow to evolve; Joint Fires Network just moved from R&D to acquisition (1 Oct 2025); Lattice was selected for Army IBCS-M in Nov 2025. The integration priority order beyond TAK is roughly DCGS → Maven/Gotham → JTT → JFN/IBCS-M.

**LE / public-safety.** Different drivers entirely from DoD. CoT is essentially absent from RTCC and RMS vendors (Axon Fusus, FlockOS, Genetec Mission Control, Mark43, Hexagon, Tyler) — confirmed wedge. CJIS Security Policy v6.0 and FedRAMP shape federal LE procurement. Civil-liberties pressure is load-bearing: Geolitica/PredPol shut down, Flock LPR lost a Washington public-records ruling, and EFF/ACLU litigation against ALPR is active. "Predictive policing" branding is poisoned — confidence must be framed as provenance and explainability, not prediction. A federated-reference data model (point to source-of-record systems) fits RISS/N-DEx posture better than centralization. ATAK-CIV adoption is real (CBP, USCG, USSS, FEMA, ICE) but workflow tooling on top of it isn't.

**AI/CV-to-CoT.** Maven Target Workbench is again the strongest validation: vertical columns, operator approve/disapprove on nominations, ~2,000 daily NORAD/NORTHCOM users in 2025. The CoT standards gap is concrete and actionable: MITRE's CoT Sensor Schema covers sensor pointing (azimuth, FOV, range, model, version) but has no confidence field, no bounding box, no detection metadata. Every vendor rolls their own `<detail>` extension. Production HITL patterns across Maven, Helsing HX-2, Switchblade 400, and Anduril Sentry cluster at "human-in-the-loop semi-autonomous" per DoDD 3000.09; none publish portable, auditable approval-log artifacts. Confidence semantics are not portable across vendors (Planet, BlackSky, YOLO, ATR scores aren't directly comparable) — cross-vendor calibration is an open problem. TAK-ML (Raytheon BBN) is the closest open-source AI-into-TAK prior art but stays ATAK-bound.

## Patterns we should lift

| Pattern | Source | Why |
|---|---|---|
| Configurable kanban columns mapped to doctrinal cycles | Maven Target Workbench | Validated by the only product directly in this space; doctrine gives names customers already use |
| `pytak` async producer/consumer + `node-tak` typed SDK | TAK community | Battle-tested CoT plumbing in two languages; do not roll our own |
| Component-based entity model internally, CoT serialization at egress | Anduril Lattice Entity API | CoT's type tree is too rigid for evolving AI detections; serialize at the boundary, not the core |
| Five-target-type taxonomy (Facility, Individual, Virtual, Equipment, Organization) | CJCSI 3370.01 | Doctrinally-blessed categorization; lets us slot into Joint workflows without negotiation |
| "AI proposes, human decides" as default with `PromotionPolicy` opt-in to autonomy | Maven, AIP, DoDD 3000.09 | Industry norm; aligns with policy direction; reduces objections from compliance/legal reviewers |
| Mission API as column backbone, transitions as native CoT events | TAK Server Mission API | Reuses existing TAK Server semantics; transitions become observable to any CoT consumer |
| Server-side plugin appears as a TAK contact | tak-gpt pattern | Zero-install UX; operator never sees Target Workspace as an external system |
| Audit/chain-of-custody as a first-class object | CJIS v6.0, DoD AI guardrails, civil-liberties pressure | Required for LE; differentiator for DoD; not implemented by anyone uniformly |
| Federated reference model (point to source-of-record systems) | RISS/N-DEx posture, fusion-center reality | Matches procurement constraints; avoids the centralization objection |
| Polyglot Source/Publisher SDK (Python + TypeScript) | Ecosystem reality | Operators write integrations in Python; web/edge integrations live in TypeScript |

## Patterns to avoid

- **Vertical monolith.** Maven and Lattice are vertically integrated. Our credibility is the opposite: open, swappable, integrable.
- **Custom CoT type tree.** The standard exists; extending the `<detail>` payload is the right surface. Don't fork the type taxonomy.
- **"Predictive" framing.** In LE markets, "predictive" branding is poisoned. Speak in terms of provenance, confidence, and explainability.
- **Ontology lock-in.** Palantir's data model is part of its moat. Ours should not be — adopt CJCSI 3370.01 + Lattice-style components, both publicly documented.
- **Reinventing CoT plumbing.** Stand on pytak / node-tak. Contribute upstream where we extend them.

## The wedge, stated precisely

Target Workspace is **a CoT-native, plugin-driven target lifecycle workspace, deployable in customer environments, accessible to anyone who already speaks TAK.** It is positioned as:

- **What Maven Target Workbench is for $1.3B-tier DoD enterprise, delivered for coalition partners, allied militaries, federal LE, state/local public safety, SAR, and expeditionary units.**
- The "Postgres to their Oracle" framing — credible because the high end has already validated the workflow.
- The standards opportunity is a published CoT `<detail>` extension for detection metadata (confidence, bbox, model version, provenance), formalized via TAK Coalition. First mover gets to define how AI detections travel through CoT.

## Risks

1. **Palantir absorbs the niche.** Maven is moving downmarket via the program-of-record transition. We need to be where Maven cannot be: coalition, allied, state/local, federal LE outside HSI, SAR.
2. **Anduril Lattice ICS dominates open architecture.** Lattice positions itself as the open backbone. If our internal entity model converges on theirs, we benefit; if they aggressively open the SDK, our plugin pitch weakens.
3. **CoT standards work outruns us.** If TAK Coalition standardizes detection metadata before we ship, we lose the standards-shaping opportunity. Engage early.
4. **CJIS / FedRAMP compliance cost.** Federal LE procurement is gated by these. Compliance posture must be in the deployment story from day one.
5. **Civil-liberties exposure in LE markets.** A poorly-framed feature (predictive scoring, opaque AI promotion) can poison the LE go-to-market. Default to explainability and audit visibility.
6. **TAK ecosystem fragmentation.** Plugin distribution is split between TAK.gov and community GitHub; getting attested for TAK.gov is non-trivial.

## Concrete design implications (feed into v0.2 of the design doc)

1. **Adopt CJCSI 3370.01 target-type taxonomy** as the categorical layer of the `Target` object. This is what the joint enterprise speaks.
2. **Ship four default board templates out of the box**: F3EAD, D3A, JP 3-60 Joint Targeting Cycle, F2T2EA Kill Chain. Plus a fifth LE template (Lead → Investigate → Validate → Action → Closed) and a sixth SAR template (Report → Triage → Assign → Search → Cleared).
3. **Internal entity model = Lattice-style components (assets/tracks/entities with disposition).** Serialize to CoT at the publisher boundary. CoT is a wire format, not an internal model.
4. **Stand on `pytak` and `node-tak`** for CoT plumbing. Do not roll our own protocol library.
5. **Mission API integration for board backbone.** Each board can optionally back-map to a TAK Server Mission; column transitions emit observable CoT events so downstream consumers see them without needing a Target Workspace-specific client.
6. **Audit / chain-of-custody is a first-class object**, not an afterthought. Every Target state change carries actor, timestamp, source, prior state, justification. Make it queryable and exportable for CJIS / DoD audit needs.
7. **Define a CoT `<detail>` extension for detection metadata** (confidence, bbox, model id, model version, provenance, source feed). Publish the schema. Pursue TAK Coalition / TPC blessing.
8. **`PromotionPolicy` defaults to gated, not autonomous.** Autonomy is opt-in per source with explicit confidence thresholds. This matches DoDD 3000.09 and reduces compliance objections.
9. **Default deployment model = customer-environment.** Airgap-clean, no required egress, FedRAMP/CJIS-friendly. SaaS is a later option, not the entry mode.
10. **Federated references over centralized copies.** Where possible, point to source-of-record systems (RISS, N-DEx, mission data sync); copy only what is required for workflow state. Reduces data-handling exposure.

## Recommended next steps

In order:

1. **Sign off on the persona roster** (separate doc) now that the prior-art frame is set. The wedge sharpens who matters.
2. **Update `v0.1-design.md` to v0.2** incorporating the design implications above. Mark the ten implications as accepted or contested.
3. **Draft full persona profiles** with the prior-art context to inform their goals and pains.
4. **Begin a short standards-watch note** tracking TAK Coalition activity on detection metadata, plus DoDD 3000.09 revisions, plus CJIS v6.0 implementation timelines — anything that affects our positioning. Update monthly.
5. **Identify open-source contributions worth making early** (pytak, node-tak, OpenTAKServer plugin model) — they build credibility before we ship.

## Source documents

- [01-tak-ecosystem.md](01-tak-ecosystem.md)
- [02-commercial-defense-tech.md](02-commercial-defense-tech.md)
- [03-doctrinal-process-tooling.md](03-doctrinal-process-tooling.md)
- [04-le-public-safety.md](04-le-public-safety.md)
- [05-ai-cv-to-cot.md](05-ai-cv-to-cot.md)
