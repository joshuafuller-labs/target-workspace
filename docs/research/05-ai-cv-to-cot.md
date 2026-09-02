# AI/CV-to-CoT Pipelines and ATR

## Landscape overview

AI-derived detections enter operator workflows today through a fragmented stack of vendor-specific pipelines, each of which terminates in some form of operator-facing surface: a vendor C2 UI, a fused common operational picture (COP), or an interoperability bus such as TAK. The dominant publish protocol on the tactical edge is Cursor on Target (CoT), an XML-based situational-awareness format that originated at MITRE and the Air Force Research Laboratory and is now the lingua franca of the TAK family (ATAK, WinTAK, iTAK, TAK Server)[1][2]. The CoT base schema describes what/when/where via `event` elements, with extensible `detail` sub-schemas used for everything from chat to video, sensor pointing, and shape geometry[1][3].

The path from raw detection to operator-actionable signal is rarely a single hop. A typical pattern is: sensor (camera, RF receiver, radar, SAR satellite) -> on-platform or edge inference (YOLO-family detectors, custom ATR models, RF classifiers) -> vendor C2 backend (Lattice, DroneShield C2, BlackSky Spectra, Maven Smart System) -> a fusion/COP layer (Maven, Lattice, ATAK) -> human-in-the-loop adjudication -> downstream action (weapons cueing, dispatch, alerting). At each hop, metadata is added, transformed, or dropped. The CoT format itself does not natively carry AI-specific fields like model version, confidence score, or bounding box; detection metadata is either encoded in custom `detail` extensions, dropped at the boundary, or simply expressed as the CoT `type` (e.g. `a-h-G` for a hostile ground entity) plus textual `remarks`[4][5].

CoT is most useful as a publish/subscribe bus once a detection has already been triaged. It was not designed as a detection pipeline format - it was designed for situational awareness sharing. That means the real engineering happens upstream of CoT: how confidences are thresholded, how false positives are filtered, how chips of imagery are routed for human review, and how nominations are promoted into the targeting cycle. The most mature production examples of this pipeline today are Project Maven / Maven Smart System (Palantir), Anduril's Lattice platform feeding Sentry Towers and counter-UAS systems, DroneShield's TAK-integrated counter-UAS stack, and the broader commercial geoint analytic-feed market (Planet, BlackSky, Maxar)[6][7][8][9].

## Key players, projects, and patterns

| Name | Type | What it does | Detection-to-CoT path | URL | Relevance |
|---|---|---|---|---|---|
| Project Maven / Maven Smart System (Palantir) | Gov program / vendor | DoD's flagship CV-and-multi-INT targeting platform; ingests EO/IR/SAR/SIGINT, runs ML detection/tracking, surfaces nominations on a kanban-style Target Workbench[6][10] | Detection -> persistent track ID across modalities -> kanban-style workbench -> human approve/disapprove -> tasking message to weapons system[6][10] | https://www.palantir.com/platforms/gotham/ ; https://defensescoop.com/tag/maven-smart-system/ | Direct prior art: Maven literally uses a kanban for target nomination[6] |
| Anduril Lattice + Sentry Tower | Vendor | AI surveillance towers (Sentry, XRST) detect/classify humans/vehicles/animals autonomously and present alerts to operators; Lattice fuses third-party data into a COP[7][8][11] | Sensor onboard ML -> Lattice EntityManager API (gRPC/REST, `anduril.ontology.v1` proto) -> Lattice COP -> operator adjudication[11][12] | https://developer.anduril.com/ ; https://www.anduril.com/sentry | Closest commercial analog to a pluggable detection-to-COP pipeline; entity ontology is component-based rather than CoT-native[12] |
| Shield AI Hivemind / V-BAT / Nova 2 | Vendor | Autonomy stack for VTOL UAS and indoor robots; Hivemind Pilot does perception, state estimation, object detection/tracking; Nova 2 auto-populates a map with detected threats[13][14] | Onboard inference -> Hivemind state estimation -> map auto-population on operator device; not natively CoT-first[13] | https://shield.ai/ ; https://shield.ai/hivemind-solutions/ | Edge-AI exemplar; demonstrates pattern of map-driven auto-population from onboard detection |
| Skydio X10D + ATAK | Vendor | Enterprise/military drone with native ATAK integration; streams STANAG 4609 KLV-tagged video and telemetry into ATAK and ATAK UAS Tool[15][16] | Drone -> ATAK UAS Tool -> if object detection enabled, image markers placed on map with frame snapshot for cars/trucks/people[15][17] | https://www.skydio.com/blog/skydio-x10d-integrates-with-atak-for-tactical-isr ; https://support.skydio.com/hc/en-us/articles/22838103434907 | Concrete production CV-to-ATAK pipeline; object detection is opt-in and creates map markers |
| DroneShield (RfPatrol, RfOne, DroneSentry-X) | Vendor | RF-based counter-UAS detection with sensor fusion across radar/RF/EO/thermal[18][19] | Sensor -> DroneShield C2 -> CoT messages -> TAK Server; RfPatrol-Plugin and RfLink ATAK plugins also exist[18][19] | https://www.droneshield.com/ ; https://www.unmannedairspace.info/counter-uas-systems-and-policies/droneshield-integrates-c-uas-command-and-control-platform-with-us-dod-tak-system/ | Production CoT publisher for AI/RF detections; exact CoT metadata fields not publicly documented[18] |
| Hidden Level | Vendor | Distributed urban RF sensing network for drone detection (including non-emitting and "dark" drones)[20] | Sensor network -> Hidden Level cloud -> integrations; specific CoT/TAK details not publicly documented[20] | https://www.hiddenlevel.com/ | Persistent RF surveillance pattern; CoT integration plausible but unverified from public sources |
| Helsing (Altra, HX-2) | Vendor | German defence AI; Altra fuses ISR drones/spotters/sensors and provides targeting info; HX-2 strike drones use ML object recognition for target detection with operator review before strike[21][22] | Multi-source ingest -> ML pattern recognition -> targeting overlay -> operator approves strike[21][22] | https://helsing.ai/ ; https://en.wikipedia.org/wiki/Helsing_(company) | European HITL-on-strike model; uses operator-review-before-engage at terminal phase |
| AeroVironment Switchblade 400 / AV_Halo | Vendor | Loitering munition with aided target recognition (ATR) and EO/IR; selected for U.S. Army LASSO program[23][24] | Onboard EO/IR + ATR -> operator-in-loop until terminal phase -> autonomous final approach[23] | https://www.avinc.com/solution/switchblade-400/ | Onboard ATR example; demonstrates confidence-and-autonomy gradient through the engagement |
| BlackSky Spectra | Vendor | Commercial geoint platform with ML-based object detection (vessels, vehicles, aircraft) and change monitoring on satellite imagery; emphasizes speed of delivery[9][25] | Satellite capture -> Spectra ML pipeline -> analytic delivery via API; CoT not native[9] | https://www.blacksky.com/ ; https://gisgeography.com/blacksky-planet-maxar/ | Pattern for confidence-tagged analytic-feed delivery, not yet CoT-native |
| Planet Analytic Feeds | Vendor | Daily-cadence analytic feeds: object detection and land-classification (buildings, vessels, roads) from PlanetScope/SkySat imagery[26] | Imagery -> classifier -> analytic feed via API/portal[26] | https://www.planet.com/products/satellite-imagery-of-earth/ | High-volume, low-latency detection feed pattern |
| HawkEye 360 RFGeo / RFIQ | Vendor | RF-emitter geolocation from satellite constellation using TDOA/FDOA; outputs metadata, not raw RF[27][28] | On-orbit RF capture -> ground processing -> geolocated emitter metadata via API[27] | https://www.he360.com/ | Pattern for delivering inferred geo-points with provenance metadata at scale |
| Logos Technologies (Kestrel, Redkite, Simera) | Vendor | Wide-area motion imagery (WAMI) sensors that record city-sized areas; "see everything, miss nothing"[29][30] | WAMI capture -> archive -> forensic and real-time activity-based intel analytics[29] | https://www.logostech.net/ | Persistent surveillance pattern; producer of dense detection candidates for downstream ATR |
| PyTAK + takproto | OSS library | Python library for building TAK clients/servers/gateways; supports TAK Protocol v0 (XML) and v1 (Protobuf) over TCP/TLS/UDP[31][32] | Any Python source -> PyTAK CoT serialization -> TAK Server[31][32] | https://github.com/snstac/pytak ; https://pypi.org/project/takproto/ | Foundational library for emitting AI detections as CoT; no built-in detection metadata schema[31] |
| cotlib (NERVsystems) | OSS library | Go library for parsing/validating/generating CoT with embedded XSD catalog and LLM-friendly search APIs; supports ~20 standard `detail` extensions[5] | Any Go source -> cotlib -> validated CoT[5] | https://github.com/NERVsystems/cotlib | High-quality CoT validation tooling; no dedicated AI-detection extension exists[5] |
| OpenTAKServer | OSS | Community TAK Server reimplementation enabling CoT ingest/distribute to ATAK/WinTAK/iTAK clients[33] | Any CoT publisher -> OTS -> ATAK clients[33] | https://github.com/brian7704/OpenTAKServer | Self-host endpoint Target Workspace can target without commercial TAK Server licensing |
| TAK-ML (Raytheon BBN) | OSS / gov-funded | ML model packaging, distribution, and on-device execution framework for ATAK; supports PyTorch/TF/TFLite/ONNX via model-execution plugins; outputs flow through a Tensor Processor producing labels[35] | Model wrapper -> ATAK on-device inference -> labeled result via callbacks or KServe-compatible API -> optional CoT publish via plugin[35] | https://github.com/raytheonbbn/tak-ml | The most direct OSS prior art for moving AI inference results into the TAK ecosystem |
| MITRE CoT Sensor Schema | Standard | CoT detail extension for steerable EO/IR/radar sensors: azimuth, elevation, roll, FOV, VFOV, range, north, type, model, version[4] | Producer-side metadata only; describes the sensor, not the detection[4] | https://github.com/deptofdefense/AndroidTacticalAssaultKit-CIV/blob/master/takcot/mitre/CoT%20Sensor%20Schema%20%20(PUBLIC%20RELEASE).xsd | Closest official extension to "detection provenance"; notably has no confidence field[4] |
| Bellingcat toolkit + GeoHints, ShadeMap | OSS / nonprofit | Curated open-source geolocation toolkit; Bellingcat experimented with LLMs (Bing/Bard) for image geolocation with poor solo results[36][37] | Manual analyst workflow; ad-hoc CoT publishing if at all | https://bellingcat.gitbook.io/toolkit/ ; https://www.bellingcat.com/resources/2023/07/14/can-ai-chatbots-be-used-for-geolocation/ | Reference for AI-augmented OSINT workflow; human-in-the-loop is heavy[37] |
| DARPA Squad X / OFFSET | Gov program | Squad X equips dismounts with autonomous sensors/UAS for situational awareness; OFFSET drives swarm tactics and human-swarm interfaces for hundreds of platforms[38][39] | Heterogeneous edge sensors -> squad-level fusion -> operator-facing UI[38][39] | https://www.darpa.mil/program/squad-x ; https://www.darpa.mil/research/programs/offensive-swarm-enabled-tactics | Research-stage prior art for AI-to-dismount detection routing |

## Confidence-gating and human-in-the-loop patterns

What's actually deployed today is narrower than the marketing implies. DoD Directive 3000.09 (updated January 2023) is the controlling U.S. policy; it does not actually mandate a human "in the loop" - it requires "appropriate levels of human judgment over the use of force" and distinguishes human-in-the-loop (semi-autonomous), human-on-the-loop (supervised), and human-out-of-the-loop (full LAWS) systems[40][41]. Practical deployments cluster at the in-loop end: Anduril Sentry generates alerts that operators "adjudicate"[7]; Maven's Target Workbench produces nominations that operators "approve or disapprove" before tasking[10]; Helsing's HX-2 strike drones use ML object recognition where the operator reviews before strike, with autonomy only in the final terminal-guidance phase[21][22]; Switchblade 400 holds the operator in the loop until similar terminal phases[23].

Confidence handling in production is mostly implicit, not standardized. Sentry's autonomous classification is binned into discrete classes (human/animal/vehicle) before alert generation - the threshold is in the vendor's pipeline, not exposed to the operator[7]. BlackSky and Planet expose ML-derived detections through analytic feeds whose schemas typically include a confidence float per detection, but the consumer is expected to apply their own threshold; this is delivered via API, not CoT[9][26]. CoT itself has no defined `confidence` field anywhere in the public MITRE schemas, including the Sensor Schema; teams that need it must either roll a custom `detail` extension or smuggle it into `remarks`[4][5]. There is no industry consensus on the field name, units, or semantics, which is a significant interoperability gap.

The most visible workflow pattern is what Maven institutionalized: a board (kanban) where detections are tracked as cards moving through analyst columns, with explicit approve/disapprove gates before any tasking message leaves the system[6][10]. NORAD/NORTHCOM reportedly had ~2,000 daily users on MSS in 2025[42], demonstrating that the kanban-style nomination flow scales operationally.

## Patterns we should consider adopting

1. **Kanban-as-targeting-workflow is validated**. Maven Smart System's Target Workbench uses a literal kanban with vertical columns representing what were previously siloed analyst processes[6][10]. Target Workspace's core hypothesis is consistent with the most expensive program in DoD AI targeting.

2. **Stable detection IDs across modalities**. Maven assigns each detection a stable identifier that follows it across satellite, drone, and CCTV feeds[6]. Target Workspace should mandate a `detection_id` (or `track_id`) that is persistent across the entire lifecycle - ingest, promotion, publish, and any republishes.

3. **Component-based entity ontology, not strict types**. Anduril Lattice models entities by the presence/absence of components rather than a strict type hierarchy[11][12]. This is a better fit than CoT's rigid hyphenated type tree for AI-derived detections where evidence accumulates over time.

4. **Confidence-gated promotion as an explicit policy primitive**. Treat confidence thresholds as workspace-level configuration, not hardcoded constants. Producers (e.g. Switchblade ATR, BlackSky, YOLO inference) all emit confidence; consumers (ATAK operators) currently don't see it. The workspace should be the place where the gate is configured and audited[9][23][26].

5. **Model-version and provenance must travel with the detection**. TAK-ML wraps models in versioned containers and surfaces results with metadata; HawkEye 360 explicitly transforms raw RF into "metadata tailored to user-defined signal processing chains"[27][35]. Provenance (model id, model version, sensor id, capture time) is part of the detection, not optional.

6. **Image chip / bbox attachment, not just a point**. Skydio's ATAK UAS Tool already places "an image marker on the map at that location with a snapshot of the video frame" for detected objects[17]. Target Workspace should treat the chip/frame/clip as a first-class attachment on the card, not a CoT afterthought.

7. **Explicit approve/disapprove gate before publish**. The Maven model and Helsing's "operator reviews before strike" model converge here: a deterministic gate, by user, with audit trail, before any CoT publication that leaves the workspace[10][21].

8. **Pluggable serialization**. PyTAK supports both legacy XML and TAK Protocol v1 protobuf transports; takproto handles three CoT message formats[31][32]. The publish side must abstract serialization the way the ingest side abstracts source format.

## Gaps and weaknesses

1. **No standard CoT extension for AI detections**. The MITRE CoT Sensor Schema covers sensor pointing but explicitly has no confidence, no bounding box, no model identifier[4]. Every vendor that needs these is rolling its own extension or putting structured data in free-text `remarks` - this is exactly the kind of interoperability hole an extensible workspace can address by proposing a schema.

2. **Confidence semantics are non-portable**. Planet's classifier confidence, BlackSky's, a YOLO model's `objectness * class_prob`, and Switchblade's ATR confidence are not directly comparable[9][23][26]. There is no calibrated cross-vendor confidence standard.

3. **Vendor lock-in at the COP layer**. Lattice, Maven Smart System, and DroneShield's C2 all want to be the COP[6][7][18]. Each ingests competitors' feeds reluctantly. CoT is the de facto neutral bus precisely because it is the lowest common denominator.

4. **Sensor metadata is dropped between hops**. STANAG 4609 KLV is preserved in Skydio's ATAK stream[15], but most CoT republishers do not carry the originating sensor's KLV, model version, or capture timestamp.

5. **OSINT-to-CoT is largely manual**. Bellingcat's toolkit is a manual analyst workflow[36]; LLM-only geolocation is unreliable[37]. There is no productized pipeline for "AI-derived OSINT location -> CoT" with auditability.

6. **Human-in-the-loop is asserted, not audited**. The 3000.09 framework defines categories but does not mandate a tamper-evident audit log of who approved which detection[40][41]. Most production systems do log approvals internally, but the artifact is not shareable across organizations.

7. **Counter-UAS interoperability is fragmented even within CoT**. DroneShield publishes CoT to TAK; Dedrone, Hidden Level, and D-Fend each have their own paths; CoT consumers receive overlapping tracks of the same emitter from multiple sensors with no entity-resolution layer above[18][20].

8. **Edge inference results often die on the device**. Skydio's optional object detection produces map markers on the controller but does not always publish them as CoT to a wider TAK network[17]. The "last mile" from edge model output to networked CoT is inconsistent.

## Implications for Target Workspace

1. **Define a first-class detection schema that subsumes what producers actually emit.** At minimum: `detection_id` (stable across republishes), `producer_id`, `model_id`, `model_version`, `capture_time`, `geometry` (point, polygon, or bbox in image and world coords), `confidence` (numeric, plus optional vendor-native value), `class` (vendor string plus our normalized taxonomy), `chip_uri` (the image/frame evidence), and `provenance_chain` (ordered list of upstream transformations). This is the data Lattice, Maven, BlackSky, Planet, Skydio, DroneShield, and TAK-ML each carry in some form[6][9][11][15][26][35]; consolidating them is the leverage point.

2. **Make confidence-gated promotion a workspace policy primitive.** Columns should be able to declare entry predicates over the detection schema, e.g. "promote when confidence >= 0.7 AND class in {vehicle, vessel}". Per Maven's pattern, the workspace - not the upstream producer - is where the gate is configured[6][10]. Policies must be auditable and versioned.

3. **Treat CoT as the publish target, not the internal model.** Internally use a richer model (closer to Lattice's component-based entity)[11][12]; serialize to CoT (XML or TAK Protocol v1 protobuf) at the egress boundary via PyTAK/takproto[31][32]. Define a `<detail>` extension (`detection` element) carrying confidence, model id, model version, and chip URI; preserve it on republish.

4. **Mandate an approval gate before any external CoT publish.** This is what Maven, Helsing, and Switchblade all converge on operationally[10][21][23], and what DoDD 3000.09 effectively asks for[40][41]. The audit log of "who promoted what when" must be immutable and exportable.

5. **Build for multiple TAK endpoints from day one.** Target TAK Server and OpenTAKServer; abstract the transport (TCP/TLS/UDP, XML/protobuf) the way PyTAK does[31][33]. Don't assume a single TAK deployment per workspace.

6. **Position the workspace to publish a calibrated, normalized confidence alongside the vendor-native value.** This addresses the cross-vendor confidence-portability gap and gives operators a single threshold dial[9][23][26]. Calibration tables can be a per-producer plug-in.

## Sources

1. https://en.wikipedia.org/wiki/Cursor_on_Target
2. https://tutorials.techrad.co.za/wp-content/uploads/2021/06/The-Developers-Guide-to-Cursor-on-Target-1.pdf
3. https://www.mitre.org/sites/default/files/pdf/09_4937.pdf
4. https://github.com/deptofdefense/AndroidTacticalAssaultKit-CIV/blob/master/takcot/mitre/CoT%20Sensor%20Schema%20%20(PUBLIC%20RELEASE).xsd
5. https://github.com/NERVsystems/cotlib
6. https://www.spatialintelligence.ai/p/inside-palantirs-maven-smart-system
7. https://www.anduril.com/sentry
8. https://www.anduril.com/news/anduril-launches-extended-range-sentry-tower-xrst
9. https://gisgeography.com/blacksky-planet-maxar/
10. https://en.wikipedia.org/wiki/Project_Maven
11. https://developer.anduril.com/guides/entities/overview
12. https://buf.build/anduril/lattice-sdk/docs/7baae0ed60e4432382ea3f338da57899:anduril.ontology.v1
13. https://shield.ai/hivemind-solutions/
14. https://shield.ai/autonomy-for-the-world-indoor-exploration-with-nova-2/
15. https://www.skydio.com/blog/skydio-x10d-integrates-with-atak-for-tactical-isr
16. https://support.skydio.com/hc/en-us/articles/22838103434907-How-to-set-up-ATAK-with-the-Skydio-X10-Controller
17. https://www.scribd.com/document/632077442/ATAK-UAS-Tool-User-Guide-10-0
18. https://www.unmannedairspace.info/counter-uas-systems-and-policies/droneshield-integrates-c-uas-command-and-control-platform-with-us-dod-tak-system/
19. https://uasweekly.com/2025/10/21/droneshield-releases-rfpatrol-plugin-for-tak-ecosystem-integration/
20. https://www.hiddenlevel.com/
21. https://en.wikipedia.org/wiki/Helsing_(company)
22. https://helsing.ai/hx-2
23. https://www.avinc.com/solution/switchblade-400/
24. https://www.avinc.com/2026/05/04/u-s-army-selects-avs-switchblade-400-for-lasso-program/
25. https://www.ainvest.com/news/blacksky-technology-bksy-revolutionizing-real-time-geospatial-intelligence-gen-3-satellites-2601/
26. https://www.planet.com/products/satellite-imagery-of-earth/
27. https://www.eoportal.org/satellite-missions/hawkeye-360
28. https://www.prnewswire.com/news-releases/hawkeye-360-announces-rfiq-product-for-a-deeper-look-at-rf-activity-using-an-industry-leading-range-of-radio-spectrum-301934587.html
29. https://www.logostech.net/
30. https://www.logostech.net/wami-surveillance-see-everything/
31. https://github.com/snstac/pytak
32. https://takproto.readthedocs.io/en/latest/
33. https://github.com/brian7704/OpenTAKServer
35. https://github.com/raytheonbbn/tak-ml
36. https://bellingcat.gitbook.io/toolkit/categories/geolocation
37. https://www.bellingcat.com/resources/2023/07/14/can-ai-chatbots-be-used-for-geolocation/
38. https://www.darpa.mil/program/squad-x
39. https://www.darpa.mil/research/programs/offensive-swarm-enabled-tactics
40. https://www.esd.whs.mil/portals/54/documents/dd/issuances/dodd/300009p.pdf
41. https://en.wikipedia.org/wiki/Department_of_Defense_Directive_3000.09
42. https://www.missiledefenseadvocacy.org/maven-smart-system/
