# Law Enforcement and Public Safety Analogues

## Landscape overview

The law enforcement and public safety (LE/PS) software market organizes itself around two doctrinal centers of gravity that differ sharply from military targeting: the **incident-and-case lifecycle** (a 911 call or tip becomes a CAD event, then an incident report, then an RMS record, then potentially a case) and the **lead-and-suspect lifecycle** inside investigative units, fusion centers, and Real-Time Crime Centers (RTCCs). Where the military "target" is an entity authorized for kinetic or non-kinetic effects under doctrinal cycles like F3EAD, the LE analogue is a "person of interest," "subject," "lead," or "case subject" — language chosen deliberately because Fourth Amendment, due-process, and civil-rights doctrine make the difference between intelligence collection and adjudicated action a legal bright line [1][2]. This produces tooling that emphasizes auditable provenance, retention controls, role-based access, and downstream evidentiary defensibility far more than military C2 tools typically do.

The RTCC has become the dominant operational pattern of the past decade. RTCCs aggregate CAD, video management (VMS), automated license plate recognition (ALPR), gunshot detection (e.g., ShotSpotter), drones, social-media monitoring, and field GPS into a "single pane of glass" that triages a continuous flood of sensor and citizen inputs and pushes actionable intelligence to officers [3][4][5]. Around RTCCs sit the federal and regional information-sharing fabrics: 80 designated state and major-urban-area fusion centers, the FBI's LEEP/N-DEx, DHS HSIN, and the BJA-funded RISS network — all of which federate searches and bulletins across jurisdictions [6][7][8]. Search and rescue (SAR) and emergency operations use a related but distinct pattern centered on Incident Command System (ICS) doctrine: a common operating picture (COP), assignment-based task boards (e.g., SARTopo segments and ArcGIS Mission tasks), and operational-period documentation [9][10].

The biggest divergence from military doctrine is civil-liberties pressure. LE tooling is expected to expose audit logs, retention timers, and access trails to internal affairs, courts, defense counsel, journalists, and oversight boards. Recent litigation — including a 2025 Washington state ruling that Flock Safety ALPR data is a public record [11], EFF/ACLU lawsuits against warrantless ALPR queries [12], and the controlled wind-down of Geolitica/PredPol after bias and accuracy critiques [13][14] — makes "what we collected, who saw it, how long we kept it, and why we acted" a first-class data model concern, not an afterthought. Any "target board" that ports military F3EAD into LE without those affordances will not survive procurement, let alone deployment.

## Key players and tools

| Tool / Vendor | Category | Workflow capabilities | TAK relationship | URL | Why it matters |
|---|---|---|---|---|---|
| Axon Fusus | RTCC platform | Unified live map of officer location, CAD, ALPR overlays, VMS feeds, drone video; certified partner integrations via Works With Axon | None advertised; parallel ecosystem | https://www.axon.com/products/axon-fusus | The dominant commercial RTCC platform after Axon's 2024 acquisition of Fusus; sets the bar for "one map, many sensors" UX [4][15] |
| Axon Records (RMS) | Cloud RMS / case management | Case lifecycle Triage to Closure with tasks, documentation, evidence linkage; tight Evidence.com integration | None | https://www.axon.com/products/axon-records | The cloud-native RMS challenger; defines what "modern" case workflow looks like to LE buyers [16] |
| Mark43 | Cloud CAD + RMS | Configurable per-agency workflows, automated auditing/versioning, configurable fields, validation, approval routes; recent DOI federal deployment | None | https://mark43.com/ | Cloud-native CAD/RMS leader; the federal-scale reference deployment (DOI, 2025) shows configurability bar [17][18] |
| Hexagon I/CAD | CAD / dispatch | Call handling, dispatching, mapping, mobile + field comms; 2,500+ agencies in 28 countries; large-event/IC workflows in 9.4 | None advertised | https://hexagon.com/products/intergraph-computer-aided-dispatch | Incumbent global CAD with deep ties; the system any LE tool must integrate with in many cities [19] |
| Tyler Enterprise Public Safety | CAD/RMS/jail/court | Records, CAD, jail admin, court integration; cloud-first; 45,000+ installations across 15,000 sites | None | https://www.tylertech.com/solutions/courts-public-safety | The "Microsoft of govtech" — installed base creates massive switching costs in state/local LE [20] |
| Flock Safety (FlockOS + LPR) | LPR + RTCC | LPR hot lists, NCIC cross-checks, FlockOS unified map (LPR, VMS, drones, CAD, gunshot, 911) | None | https://www.flocksafety.com/products/flock-os | Defines the LPR-led RTCC pattern; also the lightning rod for ALPR civil-liberties litigation [11][21] |
| SoundThinking / ShotSpotter | Acoustic sensor | <60s gunshot alert to CAD, RTCC, CCTV, LPR, drones via open APIs; integrates with mapping and drone response (e.g., Pueblo PD + BRINC) | None | https://www.soundthinking.com/law-enforcement/leading-gunshot-detection-system/ | Canonical example of a single-signal vendor that succeeds by being a polite tenant in every CAD/RTCC platform [22][23] |
| Genetec Security Center + Mission Control | VMS + incident workflow | Event correlation, SOP-driven guided workflows, dashboards, post-incident audit; Operations Center adds investigation tracking | None | https://www.genetec.com/products/operations/mission-control | Best-in-class example of SOP-guided incident workflow tied to live VMS data [24][25] |
| Milestone XProtect | VMS | Open ONVIF integration, XProtect Evidence Manager for evidence export to RMS (e.g., Axon Evidence partnership) | None | https://www.milestonesys.com/products/software/xprotect/ | The on-prem VMS LE tends to prefer for data-sovereignty reasons over Verkada's cloud [26] |
| Esri ArcGIS Mission | C2 / situational awareness | AOI definition, tactical assignments, persistent comms, real-time field updates; used for SAR, directed patrol, special events | Esri publishes CoT interop guidance; Mission consumes CoT-style position data | https://www.esri.com/en-us/arcgis/products/arcgis-mission/overview | The closest commercial analogue to a CoT-driven workspace; sits inside ArcGIS Enterprise stacks already in LE [27][28] |
| CalTopo / SARTopo | SAR mapping + IM | Segments, assignments, operational periods, ICS docs, mobile app, real-time team tracking | ATAK plugin exists (CalTopo for ATAK) | https://caltopo.com/rescue | The de-facto SAR coordination tool in the US; the "kanban" of search segments [9][29] |
| SARCOP (NAPSG/DHS S&T/FEMA) | SAR COP | Aggregates apps + geospatial analytics; multiagency real-time data sharing; 225 active responses since 2021 | Not native; complements TAK | https://www.iafc.org/topics-and-tools/resources/resource/search-and-rescue-common-operating-platform-(sarcop) | The federal-grade SAR COP; shows that "one map across many agencies" is achievable in practice [10][30] |
| D4H Incident Management | EOC / incident mgmt | Forms, tasks, logs, maps, status boards; task boards with customizable workflows; pre-plans; resource mgmt | None | https://www.d4h.com/products/incident-management-software | Closest off-the-shelf "kanban for incidents" pattern; explicitly task-board-shaped [31] |
| Maltego | OSINT graph | Person-of-interest graph traversal, OSINT + internal data fusion, dashboards, case sharing | None | https://www.maltego.com/law-enforcement/ | The link-analysis grammar LE investigators already know; a target board needs to import/export this shape [32] |
| ShadowDragon (SocialNet, Horizon) | OSINT / SOCMINT | 500+ source coverage, monitor/investigate/identity capabilities; used by DEA, State, ICE | None | https://shadowdragon.io/products/socialnet/ | Defines SOCMINT-to-lead workflow but also illustrates the civil-liberties heat zone [33][34] |
| Babel Street | OSINT / multilingual | Real-time multilingual OSINT, threat intel, AI investigations | None | https://www.babelstreet.com/solutions/ai-powered-law-enforcement | Federal-LE-grade OSINT platform; relevant for cross-border and CBP-style work [35] |
| Skopenow | OSINT / persons | Person-of-interest reports, online verification, automated OSINT fusion | None | https://www.skopenow.com/law-enforcement | Lead-generation upstream of case management; the "intake" side of a target board [36] |
| LifeRaft Navigator | OSINT monitoring | Continuous threat detection across social, deep, dark web; integrates with Kaseware and Resolver | None | https://liferaftlabs.com/ | Pattern for "monitoring queue feeds case queue" — exactly the ingest-to-workflow handoff Target Workspace needs [37] |
| Kaseware | Investigative case mgmt | Cases, incidents, evidence, link analysis, timelines, entity recognition; used by 30%+ of US fusion centers | None | https://www.kaseware.com/law-enforcement | Built by ex-FBI Sentinel team; closest off-the-shelf "case board" with fusion-center scale [38] |
| Marinus Analytics (Traffic Jam) | Counter-trafficking | Pattern detection across escort/CSAM ad data; descended from DARPA Memex | None | (Marinus Analytics product page — see [39]) | Domain-specific target board for counter-trafficking; shows niche verticalization model |
| TAK.gov LE solution / ATAK-CIV | C2 / SA | Map, BFT, plugins (LE, border, protection ops); CoT-native | Native CoT, native TAK | https://tak.gov/solutions/law-enforcement | TAK's foothold in LE: CBP, USCG, ICE, USSS, FEMA all on TAK to varying degrees; Texas TAK federates with FBI/CBP/Military [40][41][42] |
| DHS HSIN / FBI LEEP / N-DEx / RISS | Federal data fabric | Sensitive-but-unclassified portals; LEEP includes RISC, Intelink, Active Shooter; N-DEx federates incident, arrest, booking, CFS, field contact records; RISSIntel federates 32 partner DBs | None | https://www.dhs.gov/homeland-security-information-network-hsin , https://le.fbi.gov/informational-tools/national-data-exchange-n-dex | The interagency plumbing every LE target board has to play nicely with [6][7][43] |

## Patterns we should consider adopting

1. **Single-map UX with layered, toggleable sensor feeds.** Every modern LE platform — Fusus, FlockOS, Mission Control, ArcGIS Mission, SARCOP — converges on one live map where the operator toggles layers (CAD, LPR, video, gunshot, drone, BFT) rather than swapping apps [3][4][5]. Target Workspace's kanban should be paired with a persistent map view, not buried below it.

2. **Configurable per-agency workflows over fixed schemas.** Mark43 and Axon Records both market "agencies build their own workspace" as a feature, with configurable fields, validations, and approval routes [16][17]. This validates Target Workspace's column-configurability thesis and suggests we'll need configurable approval/handoff gates between columns, not just labels.

3. **Hot list / watchlist as a primitive.** Flock's LPR-hot-list flow (subscribe a plate → cross-check NCIC → alert nearest officer) [21] is the LE equivalent of a "watch this entity" subscription. A target board should treat watchlists as a first-class artifact attached to a target, with auditable subscribe/unsubscribe history.

4. **Task-board overlay for investigations.** D4H, Axon Records case tasks, and SARTopo assignments all expose a kanban-like task list scoped to an incident or case [16][29][31]. This is the strongest direct analogue to Target Workspace's columns-as-states model and confirms market familiarity with the pattern.

5. **Federated query, local control of data.** RISSIntel, LEEP, and N-DEx all favor federated search over data centralization, so agencies retain control of their records while still being searchable [6][7][43]. Target Workspace should consider a federated mode where a column move triggers a query, not a data copy, to preserve agency ownership.

6. **SOP-guided response.** Genetec Mission Control's guided workflows (step-by-step SOPs auto-attached to event types) [24] are how risk-averse agencies enforce uniform response. Columns should be able to attach an SOP checklist that the user must walk through to advance the card.

7. **Evidence-grade provenance on every signal.** Axon Records, Milestone XProtect Evidence Manager, and Kaseware all treat chain-of-custody as the spine: who saw it, who modified it, who exported it [16][26][38]. Cards in Target Workspace need an immutable provenance trail, not a "last edited by" field.

8. **Officer-safety panic affordances.** Many LE C2 tools (ATAK, Axon Officer Safety Plan, ArcGIS Mission) include a "duress / emergency" affordance bound to the person-card-in-the-field [44]. A target board for LE should have a one-tap escalation pinned to the user, not buried in a menu.

## Gaps and weaknesses

1. **Workflow is hard-coded by vendor doctrine.** Most RMS systems (Tyler, Hexagon, even Axon Records) impose a fixed case lifecycle; agencies bend their processes to fit. True column-configurable workflow that survives audits is rare. This is Target Workspace's wedge.

2. **CoT is essentially absent in LE software.** Fusus, FlockOS, Genetec, Milestone, Mark43, and Tyler do not publish CoT producer/consumer support. ATAK-CIV is the only common CoT touch point in LE, and most RTCCs do not interoperate with it [40][45]. The "publish to TAK" angle is unique.

3. **Civil-liberties affordances are bolted on, not designed in.** Recent court losses around Flock (WA public-records ruling, EFF lawsuits) [11][12] show that retention, access transparency, and FOIA-readiness were not first-class in vendor design. There is a clean opening to ship those as defaults.

4. **OSINT-to-action handoff is brittle.** Maltego, ShadowDragon, LifeRaft, Skopenow, and Babel Street each generate leads, but the handoff into RMS/case systems is via PDF export, CSV, or partnership integrations (e.g., LifeRaft↔Kaseware) [37][46]. The pipeline from "OSINT signal" to "actionable card on a board with custody" is not solved.

5. **Predictive policing has a poisoned brand.** Geolitica/PredPol's <0.5% accuracy and bias findings, then its 2023 shutdown [13][14], have made LE buyers wary of ML-driven targeting. Any "scoring" or "ranking" feature in Target Workspace needs strong explainability and human-in-the-loop framing or it will be DOA in procurement.

6. **Multi-agency case sharing is still painful.** Fusion centers exist precisely because tooling did not solve cross-agency sharing [6][8]. RISSIntel federates queries but not workflow state. There is no widely deployed "shared kanban" across multiple LE jurisdictions.

7. **Cloud data-sovereignty constraints.** CJIS Security Policy v6.0 (released January 2025) and state-level rules push LE toward on-prem or FedRAMP-authorized cloud; Verkada-style pure cloud VMS is rejected by some agencies [26][47][48]. Target Workspace will need a self-hosted / FedRAMP path early.

8. **VMS, ALPR, gunshot, and CAD vendors do not natively share a target object.** Each emits events into the RTCC dashboard; few share a common "entity" or "person of interest" object. The result is that operators reconstruct the entity manually across systems. A CoT-anchored, vendor-neutral entity model is a real gap.

## Implications for Target Workspace

1. **Ship LE board templates, not just generic kanban.** At minimum: an RTCC triage board (intake → verified → BOLO → dispatched → cleared), an investigative case board (lead → workup → suspect identified → arrest/warrant → closed), and an SAR/EOC board (reported missing → segment assigned → searched → resolved). Each template should bring its own column SOPs, retention timer defaults, and access-role defaults.

2. **Treat audit, retention, and access transparency as first-class columns of the data model, not settings.** CJIS v6.0 requires audit logs covering user identity, event type, timestamp, and outcome, retained at least one year with weekly review [47][48][49]. Cards must expose: every viewer, every column change, every export, retention timer, and reason-for-access. Defaults should be set so a FOIA officer can answer a request without engineering involvement.

3. **Differentiated RBAC for LE realities.** Beyond the usual roles, LE needs: court-sealed/expunged record handling, juvenile-record segregation, internal-affairs walls, task-force-specific compartments, and "officer-as-subject" exceptional access. The permission model should be record-, column-, and field-level, not just board-level.

4. **CoT bridge is the differentiator.** Since FlockOS, Fusus, and Genetec do not speak CoT, Target Workspace can position as the *bridge* that turns LE-grade signals (LPR hit, ShotSpotter alert, VMS analytic event, OSINT lead, 911 incident) into CoT events on a TAK Server for tactical teams (SWAT, USBP, USCG, USSS, joint task forces) — and conversely accepts CoT from ATAK-CIV users in the field as a new card on the board. That is a genuinely empty seat.

5. **Federate, do not centralize, sensitive data.** Model the "card" as a reference (URI + provenance) to source-of-truth records in CAD/RMS/VMS/OSINT systems, with column transitions firing webhooks rather than copying records. This aligns with RISS/N-DEx federation patterns [6][43], avoids "Target Workspace as the new mass-surveillance database" framing, and shortens procurement.

6. **Plan the procurement story around CJIS + FedRAMP + state procurement co-ops.** Tyler and Mark43's gravity comes from being CJIS-aligned, FedRAMP-pathed, and on state purchasing schedules. Without that posture, even a superior product will not be evaluated. CJIS v6.0 (Jan 2025) tightens AU-5/6/7/8/9 audit controls — designing to those now avoids a rewrite later [47][49].

## Sources

[1] https://www.ojp.gov/library/publications/real-time-crime-centers-integrating-technology-enhance-public-safety
[2] https://bja.ojp.gov/sites/g/files/xyckuh186/files/media/document/fusion_center_guidelines.pdf
[3] https://www.forcemetrics.com/blog/the-technology-ecosystem-of-modern-real-time-crime-centers
[4] https://www.axon.com/products/axon-fusus
[5] https://www.flocksafety.com/products/flock-os
[6] https://www.dhs.gov/fusion-centers-and-riss-centers
[7] https://le.fbi.gov/informational-tools/national-data-exchange-n-dex
[8] https://www.dhs.gov/fusion-centers-and-hidta-investigative-support-centers
[9] https://training.caltopo.com/firstresponse/course
[10] https://www.dhs.gov/science-and-technology/news/2024/09/19/feature-article-sarcop-one-team-one-mission-one-map
[11] https://www.eff.org/deeplinks/2025/11/washington-court-rules-data-captured-flock-safety-cameras-are-public-records
[12] https://www.eff.org/press/releases/lawsuit-challenges-san-joses-warrantless-alpr-mass-surveillance
[13] https://en.wikipedia.org/wiki/Geolitica
[14] https://themarkup.org/show-your-work/2023/10/02/how-we-assessed-the-accuracy-of-predictive-policing-software
[15] https://www.axon.com/newsroom/press-releases/axon-announces-new-fixed-ALPR-camera-solutions-and-next-gen-AI-advancements-to-expand-real-time-public-safety-ecosystem
[16] https://www.axon.com/help/axon-records/software/rms/cases-investigations/overview.htm
[17] https://mark43.com/platform/rms/
[18] https://mark43.com/press/u-s-department-of-the-interior-launches-enterprise-public-safety-platform/
[19] https://hexagon.com/products/intergraph-computer-aided-dispatch
[20] https://www.tylertech.com/solutions/courts-public-safety/public-safety
[21] https://www.flocksafety.com/blog/lpr-cameras-for-law-enforcement
[22] https://www.soundthinking.com/law-enforcement/leading-gunshot-detection-system/
[23] https://www.soundthinking.com/blog/how-pueblo-pd-uses-shotspotter-and-brinc-drone-integration/
[24] https://www.genetec.com/products/operations/mission-control
[25] https://callmc.com/genetec-mission-control/
[26] https://www.axon.com/partners/milestone
[27] https://www.esri.com/en-us/arcgis/products/arcgis-mission/overview
[28] https://www.esri.com/arcgis-blog/products/arcgis-mission/public-safety/three-ways-arcgis-mission-improves-daily-operations
[29] https://caltopo.com/rescue
[30] https://www.iafc.org/topics-and-tools/resources/resource/search-and-rescue-common-operating-platform-(sarcop)
[31] https://www.d4h.com/products/incident-management-software
[32] https://www.maltego.com/law-enforcement/
[33] https://shadowdragon.io/products/socialnet/
[34] https://en.wikipedia.org/wiki/ShadowDragon
[35] https://www.babelstreet.com/solutions/ai-powered-law-enforcement
[36] https://www.skopenow.com/law-enforcement
[37] https://liferaftlabs.com/
[38] https://www.kaseware.com/law-enforcement
[39] https://www.pbs.org/wgbh/nova/article/sex-trafficking/
[40] https://tak.gov/solutions/law-enforcement
[41] https://www.dhs.gov/sites/default/files/publications/5298_tak_factsheet_2020_v2.pdf
[42] https://www.cbp.gov/newsroom/spotlights/powerful-app-speeds-detection-heightens-awareness
[43] https://www.riss.net/faq/
[44] https://www.axon.com/products/osp
[45] https://en.wikipedia.org/wiki/Android_Team_Awareness_Kit
[46] https://www.kaseware.com/post/kaseware-partners-with-liferaft-to-enhance-osint-capabilities-governance
[47] https://www.compassitc.com/blog/cjis-security-policy-v6.0-key-updates-you-need-to-know
[48] https://le.fbi.gov/file-repository/cjis_security_policy_v5-9-4_20231220.pdf
[49] https://lsp.org/media/dgxluyj3/cjis_security_policy_v6-0_20241227-1.pdf
