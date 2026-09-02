# Commercial Defense-Tech Analogues

## Landscape overview

Target workflow software is one of the hottest categories in commercial defense tech, and as of 2026 the market has consolidated around three structural patterns. The first is the *kill-chain compression* pattern pioneered by Palantir's Maven Smart System (MSS): a kanban-style "Target Workbench" sits on top of a unified ontology and routes AI-derived detections through a customer-defined workflow with human approval gates at every column transition [1][2][3]. The second is the *open mesh / open-architecture* pattern, championed by Anduril Lattice, which exposes Entities, Tasks, and Tracks via a documented SDK (Go, Java, TypeScript, Python) so third parties can publish and consume target data without vendor permission [4][5][6]. The third is the *edge perception* pattern, exemplified by TurbineOne, Helsing Altra, and Shield AI Hivemind, where ML-based detection runs on the sensor or platform and the resulting tracks are pushed up to a C2 layer for human disposition [7][8][9].

The commercial gravity is enormous. Maven is now a formal Pentagon program of record with a contract ceiling of roughly $1.3B through 2029 [10][11]. Anduril's March 2026 U.S. Army enterprise contract is structured as a 10-year deal with a cumulative ceiling of $20B, of which an initial $87M task order makes Lattice the counter-UAS C2 backbone for JIATF-401 [12][13]. Helsing has reached unicorn status with a multi-product European footprint (Altra battle management, Cirra EW, Lura/SG-1 Fathom underwater) [14][15]. Onebrief, a workflow-first staff planning vendor built on Anthropic Claude, hit a $1.1B+ valuation and is integrated into "three of the four largest operational plans globally" [16][17].

What is striking for a Target Workspace prior-art read is that, despite the commercial intensity, almost none of the incumbents have made target workflow itself a first-class, configurable primitive. Maven's Target Workbench is the only public example of a customer-customizable kanban for the target lifecycle [3]. Lattice's C2 surface is map- and entity-first, not workflow-first. The remainder of the field treats the kanban (if present at all) as an internal UX detail rather than a configurable, publishable product surface. None of the big incumbents publish a first-class CoT-out interface that treats TAK Server as a peer consumer; CoT typically appears as a one-way bridge implemented by integrators (DroneShield being the cleanest counter-example) [18][19].

## Key players

| Vendor | Product | Target-workflow capabilities | TAK/CoT relationship | URL | Why it matters |
| --- | --- | --- | --- | --- | --- |
| Palantir | Gotham | Ontology of objects/links/actions; geospatial and link-analysis investigative workflows; "target management" with access-controlled, shared intelligence gathering [20][21] | No first-class CoT-out; CoT typically arrives via Maven/integrators | https://www.palantir.com/platforms/gotham/ | Reference architecture for object-and-link target modeling; defines the bar for ontology-driven analysis |
| Palantir | Maven Smart System (MSS) / Target Workbench | Kanban "anchored around a Kanban board-like interface, mapping to targeting stages that are customizable to organization-specific targeting workflow nomenclature"; AI Asset Tasking Recommender; pre-packaged target sets with legal sign-off [1][2][3] | Maven Smart System fuses satellite, drone, SIGINT into single targeting picture; routes to fire-support systems like AFATDS [22] | https://www.palantir.com/assets/.../Palantir_Target_Workbench___1_.pdf [3] | The exact product Target Workspace is implicitly competing against — and the only public confirmation that customer-configurable target-lifecycle columns are a category |
| Palantir | AIP | Agents generate proposals rather than executing; "mandatory human-in-the-loop oversight for critical or destructive actions"; ontology-aware action proposals [23][24] | Inherits Gotham/Maven integrations | https://www.palantir.com/platforms/aip/ | Defines the dominant pattern for AI-derived detections flowing into approval gates |
| Anduril | Lattice (C2, Mesh, SDK) | Entity data model with assets/tracks/geo-entities; `milView` component for disposition/environment/nationality; entity lifecycle (create/update/delete) via StreamEntities API [4][5][6]; classifies UAS/birds/helicopters/rockets in infrastructure protection [25] | Lattice Mesh is "network, sensor and system agnostic"; SDK lets third parties publish; ATAK integration demonstrated at Army EDGE23; no first-class CoT bridge in product, but CoT integrations are demonstrated by partners (e.g., DragonSync) [26][27][28] | https://www.anduril.com/lattice/ | The open-architecture benchmark; defines what an entity-first, federation-friendly target object looks like |
| Shield AI | Hivemind / Hivemind Pilot | Perception → cognition → action stack; object detection and identification block with "discernment and confidence metrics"; integrates third-party detection (Maven Smart, Dead Center) [9][29]; partnered with Palantir for C2 [30] | No direct CoT product; relies on partner C2 (Lattice, MSS) | https://shield.ai/hivemind-solutions/ | Reference for confidence-scored on-platform perception that *feeds* a C2/workflow layer |
| Helsing | Altra | "Accelerates target identification, localization, assignment and engagement"; aggregates drones, radar, EO/IR, soldier feeds into unified picture; AI prioritizes hundreds of simultaneous targets; runs on standard digital signage [8][14][31] | Designed for European interoperability with allied artillery, RC weapon stations, ISR drones; no explicit CoT/TAK statement located | https://helsing.ai/altra | European analogue; shows the "video-game style" UX trend and edge-resilient networking |
| Helsing | Cirra / Lura | Cirra: EW threat classification on Eurofighter ECR. Lura: large acoustic model for submarine classification, "10x quieter" than prior AI baselines [14][32] | Lura "designed for interoperability across allied platforms"; no published CoT mapping | https://helsing.ai/cirra / https://helsing.ai/lura | Shows the pattern of specialized AI models that *produce* target nominations rather than managing them |
| Scale AI | Donovan / Defense Llama | Public-sector LLM agents with "secure, auditable, operator-in-the-loop" workflows; fine-tuned on military doctrine, IHL, DoD AI ethics principles [33][34] | None native; designed to plug into existing C2/intel tools | https://scale.com/donovan | The "LLM-in-the-loop" pattern for intel workflow that any target tool will need to slot against |
| Vannevar Labs | Decrypt + IO Overwatch/Local | OSINT/foreign-language end-to-end workflow; entity extraction, sentiment, narrative analysis over ~1 PB adversarial corpus growing ~10 TB/week; Talisman Sabre 25 agentic deployment [35][36][37] | No public TAK/CoT story | https://www.vannevarlabs.com/ | Demonstrates non-kinetic "target" workflow (influence operations) and an agentic-AI baseline |
| Primer | Primer Enterprise Platform / Engines | Precomputed entities/claims/relationships across text, audio, video, image, geospatial; composable NLP engines [38][39] | None native; integration-only | https://primer.ai/ | Reference for traceable, source-spanned entity extraction feeding downstream workflow |
| Rebellion Defense | Iris on SensorOS | Fusion tracker handling "16,000+ objects" with sub-200ms latency claims; designed to embed into third-party platforms; April 2025 Navy contract expansion for target recognition [40][41][42] | Embeds into existing C2; CoT not the primary surface | https://rebelliondefense.com/products/iris/ | Reference for "embedded fusion tracker" rather than standalone UI |
| DroneShield | DroneSentry-C2 / RfPatrol-Plugin | AI sensor-fusion C2 for counter-UAS; auto-classifies Friendly/Neutral/Hostile/Unknown via Remote ID + serial; DroneOptID auto-slew/validate/track [43][44][45] | Native CoT and TAK plugin; RfPatrol-Plugin renders detections directly on CivTAK as cards; both sensors and C2 implement CoT to TAK [18][19][46] | https://www.droneshield.com/products-software | Cleanest public example of CoT-first publication from an AI-derived detection pipeline |
| BAE Systems | GXP (Joint ISR, Xplorer) | Geospatial exploitation; injects corrected KLV metadata into drone video at the edge; "weapon-quality coordinates" extraction for targeting [47][48] | KLV/STANAG 4609 lineage; TAK adjacency through KLV but not a primary CoT publisher | https://www.geospatialexploitationproducts.com/ | The incumbent ISR exploitation pipeline that Target Workspace would either ingest from or replace |
| Leidos | Airborne ISR / TCPED | Tasking, Collection, Processing, Exploitation, and Dissemination integration; airborne MEPs and C2 mission networks [49] | Integrator-led; CoT used wherever a customer prescribes | https://www.leidos.com/markets/defense/airborne | Shows the "prime integrator" path to target workflow — slow, high-cost, customer-bespoke |
| Northrop Grumman | IBCS | "Any sensor, best shooter"; track classification, threat evaluation, weapon assignment via predefined ROE plus human input; first 100 systems delivered in early 2025 [50][51][52] | TADIL/Link-16 lineage; no public CoT story as a primary interface | https://www.northropgrumman.com/...integrated-battle-command-system-ibcs/ | The kinetic air/missile defense reference for engagement-quality target objects and ROE encoding |
| Saab | 9LV CMS | Naval Combat Management System: sensor fusion (Track Data Fusion Engine), threat evaluation, weapon assignment; integrates with EOS 500 and CEROS 200 fire control [53][54] | Maritime CMS lineage; not a CoT-native product | https://www.saab.com/products/9lv-cms | European naval analogue; defines the bar for high-tempo sensor-to-shooter loops |
| TurbineOne | Frontline Perception System (FPS) | Edge AI detection on heads-up displays and drones; "detection-to-action timelines under 60 seconds"; Sep 2025 $98.9M Army IDIQ for AI/ML automated target recognition [7][55] | No CoT product story; partner-integrated | https://www.turbineone.com/ | Reference for "no-code" model authoring at the edge that produces feeds into workflow tools |
| Onebrief | Onebrief platform | Agentic workflows on Anthropic Claude; contextual planning, automated intelligence processing, multi-domain coordination, COA development; live on SIPR and JWICS [16][17][56] | None native | https://www.onebrief.com/ | Reference for collaborative-document UX (not kanban) on classified networks |

## Patterns we should consider adopting

1. **Customer-configurable column nomenclature.** Maven's Target Workbench is "anchored around a Kanban board-like interface, mapping to targeting stages that are customizable to organization-specific targeting workflow nomenclature" [3]. Different combatant commands, services, and partners use different doctrinal terms (F2T2EA, D3A, Find/Fix/Track/Target/Engage/Assess). Target Workspace's "user-defined columns" thesis is directly validated by this — and Maven shows that even the largest customer wants the freedom to rename and reorder, not just configure visibility.

2. **Pre-packaged "target sets" as a workflow primitive.** Maven generates "pre-packaged target sets with weapons assigned and legal sign-offs already in the system" to support 90+ simultaneous strikes [1]. Even outside the kinetic case, the underlying primitive — a *bundle of targets with associated approvals* — is a useful abstraction Target Workspace could expose as a first-class object (e.g., a "set" view on top of cards).

3. **Entity lifecycle as the contract.** Lattice's Entity model exposes a deterministic create/update/delete lifecycle and a StreamEntities API that emits state changes [5][6]. For a kanban that needs to react to upstream detection updates, this is the cleanest data contract: columns are the workflow, entities are the things being moved, and every state change is a stream event.

4. **Disposition as a typed component.** Lattice's `milView` component encodes disposition, environment, and nationality on every track [5]. This is more robust than a free-text "type" field and maps directly to CoT's `affiliation` attribute (hostile, friend, neutral, unknown). Adopting `milView`-compatible disposition would give Target Workspace immediate interoperability with both Lattice and CoT consumers.

5. **AI agents produce proposals, humans decide.** Both Palantir AIP and Maven explicitly require "mandatory human-in-the-loop oversight for critical or destructive actions" and surface AI outputs as *proposals* refined by an operator [23][24]. For Target Workspace this argues for a "proposed" sub-state inside every column — AI moves the card to a *suggested* destination, a human commits the transition.

6. **Confidence as a first-class attribute on the card.** Maven uses confidence to surface candidate detections; Project Maven engineers reported "90+% confidence" baselines on vehicle detection [57][58]. DroneShield surfaces classification (Friendly/Neutral/Hostile/Unknown) explicitly on every track [44]. Target Workspace should treat detection confidence as a structured, filterable, threshold-able attribute, not a notes field.

7. **Auditable state diff per transition.** Maven's "legal sign-offs already in the system" only works because every transition is auditable. The broader compliance literature (NIST AI RMF, ISO 42001, EU AI Act) converges on capturing the state diff at each gate as the artifact of record [59]. For a system that may be used in CONUS law-enforcement and DoD contexts, audit trail per column transition is table stakes.

8. **Federation over a stream API.** Lattice's StreamEntities pattern and CoT's pub/sub-style routing both reward systems that treat federation as a stream-of-state-changes rather than a query-the-database integration [5][60]. Target Workspace's ingest/publish design should optimize for streaming both directions, with each card update producing a CoT-out event consumable by TAK Server.

## Gaps and weaknesses

1. **Vendor lock-in around custom ontologies.** Critics consistently flag Gotham/Foundry's deep customization as a lock-in vector: "the deep integration Gotham requires can make it difficult and costly to switch ... long-term reliance on a sole provider can lead to higher cumulative fees" [61]. Palantir's response — that data is exportable — does not address the workflow logic, role configuration, and institutional knowledge embedded in the platform. A simpler, configurable kanban with portable workflow definitions is a real wedge.

2. **Closed CoT story.** The biggest commercial platforms either do not publish CoT natively (Gotham, AIP, Lattice C2 in the product itself) or treat it as a downstream bridge to be implemented by partners. DroneShield is the cleanest counter-example, and even there CoT is positioned as one output among many [18][19][46]. There is no commercially-prominent target-workflow product that treats TAK Server as a peer consumer from day one.

3. **Pricing exclusion.** Maven's ceiling is ~$1.3B; Lattice's enterprise contract is $20B over 10 years; Gotham GSA pricing is reported at ~$141K per core for a perpetual license [10][12][62]. These are products that lock out coalition partners, foreign militaries, U.S. state and local agencies, and small expeditionary teams who cannot stand up a Palantir/Anduril relationship. The price-point gap below the primes is real.

4. **Kanban is incidental, not the product.** Maven's Target Workbench is the only public surface that names a kanban as a first-class artifact. Lattice C2, Helsing Altra, Rebellion Iris, and Onebrief all treat their target/queue surfaces as views inside a larger app rather than configurable, publishable workflow definitions. None of them ship a *workspace abstraction* in the sense of "create a new kanban with these columns and these ingest sources."

5. **No swappable detection backends in the kanban tier.** Most products bind detection tightly to the C2 layer (Lattice's own ML models, Helsing's Altra perception, Shield AI's Hivemind). The exceptions (Hivemind integrating "Dead Center, Maven Smart") prove the rule [9]. A workflow tool that genuinely treats OSINT, CV/ATR, manual, and sensor backends as interchangeable pluggable adapters is rare to non-existent.

6. **OSINT and kinetic targeting are not unified.** Vannevar and Primer do non-kinetic OSINT workflow; Maven and Lattice do kinetic targeting. There is no commercial product that lets a workspace owner define a "narrative target," an "infrastructure target," and a "vehicle target" in the same kanban with different columns and integrations — even though that is exactly what gray-zone and counter-influence operators want.

7. **Edge-to-headquarters latency.** TurbineOne advertises sub-60s detection-to-action at the edge [7], but its workflow integration depends on the partner C2. The handoff from edge detection (TurbineOne, Helsing, Shield AI) to workflow disposition (Maven, Lattice) is often a manual or semi-manual step. A kanban that natively subscribes to edge feeds would close this gap.

8. **European/coalition friction.** Helsing's Altra is European-first; Maven/Lattice are U.S.-first. Coalition operations require both — and a TAK-native, CoT-first tool sits naturally at the seam. None of the incumbents lead with coalition data-sharing semantics; they treat them as enterprise integration projects.

## Implications for Target Workspace

1. **Make CoT publication a first-class output, not a plugin.** Every card state change should emit a CoT event consumable by TAK Server and any CoT-compatible client. This is the single most defensible differentiator versus the primes [60][18].

2. **Design the workflow definition as portable data, not configuration UI state.** A workspace's columns, transitions, gates, and ingest adapters should be a versionable artifact (JSON/YAML) that can be exported, diffed, and reproduced — directly addressing the Gotham/Foundry lock-in critique [61].

3. **Treat detection sources as adapters, not integrations.** OSINT (Vannevar/Primer pattern), CV/ATR (TurbineOne/Helsing/Shield AI pattern), manual entry, and direct sensor pub (DroneShield pattern) should all conform to the same internal target object — a card with a typed disposition, confidence, geometry, and provenance.

4. **Adopt a `milView`-compatible disposition model.** Affiliation, environment, and nationality should be required structured fields on every card, mappable both to Lattice's Entity model and to CoT's `affiliation` attribute [5][60]. This is the cheapest interop win available.

5. **Build the "AI proposes, human decides" pattern into the column itself.** Each column should support both a "current" set and a "proposed" set, with AI agents moving cards into "proposed" and humans confirming the transition. This aligns with Palantir AIP's published HITL pattern and is the regulatory minimum for any AI-derived target action [23][24].

6. **Pricing target: explicitly below the primes.** The competitive whitespace is coalition partners, allied militaries, U.S. state/local CUAS programs, and expeditionary teams who are priced out of Maven/Lattice/Gotham. A workspace-priced (per-workspace or per-seat) model in the low five- to low six-figure range per year would be transformational at this layer.

## Sources

[1] https://winbuzzer.com/2026/03/16/palantir-demos-military-ai-war-plans-xcxwbn/
[2] https://www.spatialintelligence.ai/p/inside-palantirs-maven-smart-system
[3] https://www.palantir.com/assets/xrfr7uokpv1b/1IqzwzpemtBSm98TNCczao/49bbc30cbec4d2d4d189ab27bd07376c/Palantir_Target_Workbench___1_.pdf
[4] https://www.anduril.com/lattice/lattice-sdk
[5] https://developer.anduril.com/guides/entities/overview
[6] https://developer.anduril.com/reference/overview/overview
[7] https://www.turbineone.com/
[8] https://helsing.ai/altra
[9] https://shield.ai/hivemind-solutions/
[10] https://defensescoop.com/2025/05/23/dod-palantir-maven-smart-system-contract-increase/
[11] https://defensescoop.com/2026/04/15/palantir-maven-smart-system-pentagon-program-transition-feinberg/
[12] https://breakingdefense.com/2026/03/army-awards-anduril-counter-drone-task-order-as-first-in-new-20b-contract-vehicle/
[13] https://insideunmannedsystems.com/u-s-army-enterprise-contract-with-anduril-positions-lattice-as-core-platform-for-c-uas-operations/
[14] https://en.wikipedia.org/wiki/Helsing_(company)
[15] https://thedefensepost.com/2025/05/14/helsing-unveils-ai-based-underwater-detection-system-for-quieter-threats/
[16] https://www.onebrief.com/
[17] https://sapphireventures.com/blog/the-ultimate-command-operating-system-for-global-defense-why-were-excited-to-co-lead-onebriefs-200m-series-d/
[18] https://www.unmannedairspace.info/counter-uas-systems-and-policies/droneshield-integrates-c-uas-command-and-control-platform-with-us-dod-tak-system/
[19] https://uasweekly.com/2025/10/21/droneshield-releases-rfpatrol-plugin-for-tak-ecosystem-integration/
[20] https://www.palantir.com/platforms/gotham/
[21] https://www.palantir.com/docs/foundry/object-link-types/enable-gotham-integration
[22] https://en.wikipedia.org/wiki/Project_Maven
[23] https://www.klover.ai/palantir-ai-strategy-path-to-ai-dominance-from-defense-to-enterprise/
[24] https://www.palantir.com/platforms/aip/
[25] https://www.anduril.com/lattice/mission-autonomy
[26] https://breakingdefense.com/2024/12/decentralizing-battle-data-cdao-anduril-open-tactical-mesh-to-third-party-developers/
[27] https://www.unmannedsystemstechnology.com/2023/06/anduril-demonstrates-lattice-for-mission-autonomy-at-us-army-edge23-exercise/
[28] https://github.com/alphafox02/DragonSync
[29] https://shield.ai/the-critical-role-of-perception-in-autonomous-systems/
[30] https://shield.ai/shield-ai-palantir-mission-autonomy-and-c2-working-as-one/
[31] https://defence-industry.eu/helsing-involved-in-british-armys-asgard-project-to-improve-targeting-and-battlefield-effectiveness/
[32] https://helsing.ai/cirra
[33] https://scale.com/donovan
[34] https://scale.com/blog/defense-llama
[35] https://www.vannevarlabs.com/
[36] https://research.contrary.com/company/vannevar-labs
[37] https://www.vannevarlabs.com/blog/2025/09/09/deploying-agentic-ai-at-talisman-sabre-25/
[38] https://primer.ai/
[39] https://primer.ai/products/primer-analyze/
[40] https://rebelliondefense.com/products/iris/
[41] https://rebelliondefense.com/
[42] https://thedefensepost.com/2024/05/03/us-target-recognition-solution-rebellion/
[43] https://www.droneshield.com/products-software
[44] https://www.unmannedairspace.info/counter-uas-systems-and-policies/droneshield-updates-dronesentry-c2-with-object-classification-and-tracking-improvements/
[45] https://soldiersystems.net/2026/04/08/droneshield-advances-decision-advantage-with-q2-2026-software-release-as-drone-threats-scale-globally/
[46] https://www.droneshield.com/media/press-releases/dronesentry-c2-comprehensive-dashboard-for-the-c-uas-mission-1
[47] https://www.geospatialexploitationproducts.com/wp-content/uploads/2025/01/Joint-ISR__Datasheet.pdf
[48] https://www.businesswire.com/news/home/20260514728440/en/BAE-Systems-GXP-and-Vantor-Bring-High-Accuracy-Targeting-to-New-Drone-Platforms-in-Contested-Environments
[49] https://www.leidos.com/markets/defense/airborne
[50] https://www.northropgrumman.com/what-we-do/missile-defense/integrated-battle-command-system-ibcs
[51] https://www.army-technology.com/projects/integrated-battle-command-system-ibcs-usa/
[52] https://bulgarianmilitary.com/2025/01/29/northrop-delivers-100th-integrated-battle-command-system-to-us/
[53] https://www.saab.com/products/9lv-cms
[54] https://en.wikipedia.org/wiki/9LV
[55] https://www.businesswire.com/news/home/20250904941690/en/Army-Awards-TurbineOne-Contract-for-AI-Powered-Edge-Target-Recognition
[56] https://www.onebrief.com/solutions/workflows
[57] https://d3.harvard.edu/platform-rctom/submission/project-maven-machine-learning-in-the-military-target-selection-process/
[58] https://defensetalks.com/united-states-project-maven-and-the-rise-of-ai-assisted-warfare/
[59] https://www.digitalapplied.com/blog/agentic-workflow-approval-gate-framework-governance
[60] https://www.mitre.org/sites/default/files/pdf/09_4937.pdf
[61] https://hash.ai/blog/the-problem-with-palantir
[62] https://datawalk.com/palantir-pricing/
