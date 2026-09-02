# Ukraine UAS / Fires / Targeting — Alignment Check

> **Purpose:** An honest "are we on track" audit of Target Workspace's defaults
> against what's actually being fielded in Ukraine (2022–2026). This is not a
> procurement deck or a sales pitch — it's me reading public reporting and
> checking whether our primitives line up with how operators actually work.
>
> **Audit date:** 2026-05-17. Public-source only; no classified or proprietary
> material.

---

## What's deployed in Ukraine — the short version

Ukraine fights with a **federated mesh of small, mostly-Android tools** that
talk to a **central battle-management hub**, not a single monolithic platform.
The hub is **Delta**. Around it orbit:

| Tool | Layer | What it does in the workflow |
|---|---|---|
| **Delta** | Hub / C2 / SA | Real-time digital map of friendlies + enemies + sensors. Cloud-native, multi-device, offshore-hosted for survivability. Eight situational-awareness centers feed it. Roughly 600K+ enemy-object submissions per month. CoT/TAK + Link 16 interop. NATO-validated at CWIX24. |
| **Kropyva** | Fires (artillery) | Android tablet/phone app. Operator types target coordinates (from drone, radar, FO call) → app picks the nearest available battery with the right ammo → computes a firing solution including meteorological correction → transmits to gun crews. 90–95% adoption in Ukrainian artillery units. Built by Army SOS volunteers in 2014. |
| **GIS Arta** | Fires (artillery) | Similar artillery coordinator, ~1-minute targeting reported. Predates the full-scale war. Coexists with Kropyva. |
| **Hrafit** | Fires (artillery) | Newer artillery coordination tool integrated with Delta. |
| **Virazh** | UAS | Drone flight planning. Integrated with Delta. |
| **Saker Scout** | UAS + AI | Recon UAV with on-board AI classifier — identifies 64 Russian platform types under camouflage, auto-transmits coordinates to command. Pairs with FPV kamikaze drones for the strike leg. |
| **Vyriy** | UAS | Drone OEM; integrating The Fourth Law's TFL-1 autonomy module into their FPV platform. |
| **ATAK** | Tactical display | Active Ukrainian use as a Delta client over TLS to TAK Server. CoT is the wire format. |

The operational tempo this stack produces:

- **Pre-war (2022):** detection → strike ≈ 72 hours
- **2023 average with Delta:** ≈ 2 minutes
- **2024 reported record:** **80 seconds** detect → destroy (Krynky operations)
- **Late 2025:** Delta claims **2.2 seconds** for enemy-equipment detection (the detection leg only — strike is separate)

For comparison, Western tactical targeting cycles outside of pre-coordinated
TST windows often still measure in tens of minutes to hours. Ukraine is two
orders of magnitude faster, and they did it with cheap Android tablets and
volunteer-grade software.

---

## What Target Workspace already gets right

Cross-checking the architecture I've shipped against Ukrainian practice:

1. **CoT as the wire format.** Matches Delta + ATAK + Kropyva integrations. The
   raw_cot publisher we ship is the lowest-common-denominator path; future
   tak_server adapter (tw-syn) closes the loop with full TAK Server semantics.

2. **Plugin contract (`Source` / `Publisher`).** Maps directly to the
   federated reality. Each Ukrainian tool is effectively a plugin — Saker
   pushes targets up, Kropyva pulls them down. Our `entry_points` discovery
   means a community Kropyva adapter is a `pip install` away.

3. **Editable every-CoT-field + audit-attributed updates** (shipped 2bd1103).
   Operators in Delta refine tracks as new sources arrive; the field needs to
   be mutable with provenance preserved. Our `PATCH /v1/targets/{id}` + diff
   metadata in the audit log matches that practice.

4. **Geometry beyond point — ellipse + polygon** (shipped bb459ab). EW
   single-collector LOB returns are inherently ellipses; area incidents
   (shelter footprints, flood polygons) are polygons. We model both natively
   now. **This is exactly the kind of seam Ukrainian EW units need.**

5. **Approval-gated columns** (FINISH / ENGAGE / VALIDATE). Matches RoE
   gating practice — kinetic effects require explicit authorizing-role
   capture. Our `requires_approval: true` with the ApprovalPrompt UI ships
   this discipline by default.

6. **Realtime WS fanout.** Delta's "everybody sees the same picture in real
   time" is load-bearing. Our `/v1/subscribe` with workspace-scoped events
   delivers the same primitive at smaller scale.

7. **Append-only audit chain with actor + justification + diff.** Delta's
   tiered-access + accountability story depends on knowing who did what
   when. We have it.

8. **Malleability (ADR 0008).** The Ukrainian stack is the malleability
   thesis vindicated — same primitives (map, targets, fires) reshaped for
   artillery, drones, EW, SAR by different teams. Our scenario YAML +
   theme + plugin model expects exactly this kind of community-driven
   forking.

## What Ukrainian practice exposes as gaps for us

In rough order of demo-impact and product-fit:

### 1. Sensor-to-shooter freshness is a first-class metric, not just a timestamp

Cards display `time` and `version` today. What they don't surface is **how
old this contact is right now**, which is the question every operator asks
first. In a 2-minute kill chain world, a target older than 5 minutes is
effectively cold.

**Adjustment:** Add a per-card freshness indicator — color-coded badge
(`< 1 min` / `< 5 min` / `< 15 min` / `stale`) plus a workspace-configurable
freshness threshold. Already have `target.time` and `target.stale`; we just
need to surface their delta in the SPA. Maps cleanly to ADR 0010's
source-observed-time discipline.

### 2. Effector matching is missing — we publish, we don't match

Kropyva's killer feature isn't its tablet UI. It's that the operator enters
coordinates and the system **automatically picks the nearest qualified
shooter and computes a firing solution**. Today we have `Publisher` (broadcast
out) and `Source` (ingest in) but nothing in between that says "given this
target, which available effector applies?"

**Adjustment:** Add a third plugin contract — `Effector` — that, given a
target + workspace inventory, returns a ranked list of available shooters
(unit / weapon / ammunition / range / time-to-effect / CDE level). A
demo-stub `manual_effector` ships first; community adapters for Kropyva,
TAK fires-net, NATO MIP can drop in later. This is also the seam where
"available-MQ-9-with-Hellfire-loadout" or "C-UAS Coyote SRT battery"
becomes a queryable thing instead of free text in `custom_fields`.

### 3. AI classifier output has no standardized shape

`Saker Scout` emits {class_label, confidence, bounding_box, sensor_id}. So
do every commercial CV/ATR pipeline. We carry `confidence` first-class but
the rest disappears into `custom_fields` with no convention. Means community
adapters can't reliably feed downstream AI-classifier-aware tooling.

**Adjustment:** Document a `target.classification` convention as a structured
sub-dict under `custom_fields`:

```yaml
classification:
  model_id: "saker-scout-v3.4"
  class_label: "BTR-82A"
  taxonomy: "milstd-2525-mods-2024"
  confidence: 0.91
  bounding_box_pixel: [120, 88, 142, 124]
  alternates:
    - {class_label: "BTR-80", confidence: 0.42}
```

Soft convention (not a model change) so community plugins can opt in
without a schema bump. Pairs naturally with the `source` attribution field
we just shipped.

### 4. Federation between workspace instances is unsupported

Delta works because a battalion's picture rolls up into a brigade's picture
rolls up into a division's. Our default model is one workspace per
deployment. Cross-instance sync today would require manual export/import.

**Adjustment:** New publisher plugin: `tw_mesh` — publishes `target.*` and
`audit.*` events to peer Target Workspace instances over mTLS+gRPC. Tiered
access enforced by column-filter + role-filter on the publisher config.
Single feature flag for "federate to: [list of peer URLs]" per workspace.
The realtime broker already emits the events; this is wiring them to
external sinks.

### 5. "Bearing-only" / approximate-geometry semantics need a UI affordance

We added the ellipse primitive (good). What we didn't add is the
*operational meaning* — a single-collector LOB is a low-confidence
geometry that **shouldn't be eligible for kinetic engagement** until
corroborated. Today the workflow doesn't know the difference between a
0.05 km² ellipse from a tri-sensor fusion and a 4 km² LOB from a single
collector.

**Adjustment:** Add a `geometry_quality` enum to `Target`:
`confirmed | corroborated | single-source | bearing-only`. Approval-gated
columns can check `geometry_quality >= corroborated` as a precondition on
kinetic effectors. The DF-LOB-04 demo target should land as
`bearing-only`; PANTHER-09 should be `corroborated`.

---

## Lessons from how Delta itself was built that we should internalize

CSIS's case study (cited below) names design moves that directly support our
ADR principles. Worth flagging because they're easy to drift away from:

- **Bottom-up, one capability first.** Delta started as a digital map. Other
  apps integrated around it later. ADR 0008 (malleability) is congruent.
  Resist the urge to ship "everything plugin" before the kanban + map +
  audit core is rock solid.

- **30+ releases in year one.** Their iteration speed is the moat. Our
  pre-commit + CI + bd-as-live-state discipline supports this; we should
  keep the gate to "ship today" friction low.

- **Cloud-hosted, multi-device.** Already our default (SQLite hobby tier,
  Postgres networked tier, FastAPI mountable behind any reverse proxy).
  No change needed; just don't accidentally couple to a single platform.

- **Frontline-input as a first-class data stream.** Delta receives raw
  observations from infantry, not just curated targets from intel cells.
  Our manual-entry Source covers this in principle; the mobile MVP track
  (ADR 0012, tw-h6s) is where this gets real.

## What we don't know

Honest gaps in this analysis where public reporting is thin and I'd want a
real interview before committing to product moves:

- **Actual Delta wire format details.** "CoT" is stated; the exact dialect
  extensions are not public. A Kropyva integration would need real packet
  captures.
- **Saker Scout's classifier output schema** — described qualitatively, never
  shown in a documented spec.
- **Federation protocol between Delta instances / tiers.** Stated to exist;
  implementation undocumented in public sources.
- **Counter-EW + GPS-denied operations** — frequently discussed at high level
  in CEPA / SLD reports; almost no operational detail in unclassified sources.

A pilot partner or design-partner conversation (tw-91t) would close most of
these.

## Concrete adjustments — bd issues to file

1. **`time_since_observed` / freshness indicator on cards + map** *(SPA, demo
   value high, ~½ session)*
2. **`Effector` plugin contract** *(architecture, post-MVP, ~1 session +
   ADR)*
3. **`target.classification` custom-fields convention** *(docs + one sample
   plugin update, ~2 hours)*
4. **`tw_mesh` federation publisher** *(architecture, post-MVP, ~1 session
   + ADR + threat model)*
5. **`geometry_quality` enum + approval-gate hook** *(data model + workflow
   engine, ~½ session, pairs with bb459ab)*

I'll file these as bd issues with the alignment-check label so the
provenance back to this audit is preserved.

---

## Sources

- [Delta (situational awareness system) — Wikipedia](https://en.wikipedia.org/wiki/Delta_(situational_awareness_system))
- [Does Ukraine Already Have Functional CJADC2 Technology? — CSIS](https://www.csis.org/analysis/does-ukraine-already-have-functional-cjadc2-technology)
- [Understanding the Military AI Ecosystem of Ukraine — CSIS](https://www.csis.org/analysis/understanding-military-ai-ecosystem-ukraine)
- [Battlefield Innovation: Ukraine's DELTA System at CWIX24 — NATO ACT](https://www.act.nato.int/article/delta-system-cwix/)
- ["Kropyva" Tablets for Defenders — Maibutnie Fund](https://maibutniefund.org/en/report/kropyva-tablets-for-ukrainian-defenders/)
- ["Kropyva" operates aptly — Ukrainian GUR](https://gur.gov.ua/en/content/kropyva-diie-vluchno)
- [How Ukraine turns cheap tablets into lethal weapons — Al Jazeera](https://www.aljazeera.com/news/2022/8/26/how-ukraine-turns-cheap-tablets-into-lethal-weapons)
- [Ukrainian Forces Get an AI-Powered Saker Scout Drone — Defense Express](https://en.defence-ua.com/weapon_and_tech/ukrainian_forces_get_an_ai_powered_saker_scout_drone_and_its_algorithms_can_solve_an_important_problem-7842.html)
- [Ukraine approves AI-enabled Saker drone for combat — Shephard](https://www.shephardmedia.com/news/uv-online/ukraine-approves-ai-enabled-saker-drone-for-use-in-combat/)
- [The Algorithm of Victory: Ukraine's AI-Powered Hunter-Killer Drones — TechUkraine](https://techukraine.org/2025/09/17/the-algorithm-of-victory-ukraine-unleashes-a-new-generation-of-ai-powered-hunter-killer-drones/)
- [The Heart of War: Ukraine's Key Drone Battlefield System — CEPA](https://cepa.org/article/the-heart-of-war-ukraines-key-battlefield-system/)
- [80 Seconds from Detection to Destruction in Krynky — UAS Vision](https://www.uasvision.com/2024/01/10/80-seconds-from-detection-to-destruction-in-krynky-russian-troops-have-just-one-minute-of-safety-from-ukraines-drones/)
- [Adaptation Under Fire: Russia's Kill Chain In Ukraine — CEPA](https://cepa.org/comprehensive-reports/adaptation-under-fire-mass-speed-and-accuracy-transform-russias-kill-chain-in-ukraine/)
- [Ukraine as a Kill Web Laboratory — Second Line of Defense](https://sldinfo.com/2026/04/ukraine-as-a-kill-web-laboratory-democratic-isr-grids-enabling-adaptive-drone-warfare/)
