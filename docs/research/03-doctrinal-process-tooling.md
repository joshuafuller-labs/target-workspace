# Doctrinal and Process Tooling

## Landscape overview

The U.S. military's approach to targeting is not a single workflow but a layered set of doctrinal cycles that operate at different time horizons and echelons. At the strategic and operational level, Joint Publication 3-60 codifies a six-phase Joint Targeting Cycle that begins with the commander's end state and ends with assessment.[1] At the Army tactical level, FM 3-60 (August 2023, which replaced ATP 3-60) and its D3A methodology (Decide, Detect, Deliver, Assess) sit underneath the joint cycle and feed it.[2][3] Special operations forces and the intelligence community generally use F3EAD (Find, Fix, Finish, Exploit, Analyze, Disseminate), a loop optimized for intelligence-driven manhunting that emerged from counter-terrorism operations after 9/11.[4][5] The Air Force speaks in terms of a kill chain — F2T2EA (Find, Fix, Track, Target, Engage, Assess) — codified in AFDP 3-60 and historically associated with General John Jumper's late-1990s drive to compress dynamic targeting to single-digit minutes.[6][7] Doctrine deliberately distinguishes deliberate targeting (days/weeks horizon, planned through the JIPTL into an ATO) from dynamic targeting (current 24-hour fight, executed against time-sensitive targets).[8]

Sitting on top of doctrine is a sprawling tooling layer that has evolved over four decades. Some systems are heavyweight programs of record — TBMCS for air tasking orders, GCCS-J for the common operational picture, DCGS variants for ISR processing/exploitation/dissemination (PED), and the Joint Targeting Toolbox (JTT) for the back-end target folder and weaponeering workflow.[9][10][11][12] On top of and increasingly displacing these, a newer generation of commercial software — Palantir Gotham/Maven Smart System, Anduril Lattice, and the cross-service Joint Fires Network — promises faster, AI-assisted target-to-shooter pairing as part of the broader JADC2 vision.[13][14][15]

Underneath every one of these systems are the same data primitives: target objects (BE numbers, target reference points), prioritized lists (the JTL, JIPTL, RTL, NSL, HVT/HPT lists), and gate artifacts (CDE assessments, ROE constraints, vetting and validation records).[16][17] A workspace product that ingests CoT and publishes CoT therefore lives in a stack that already has a strong opinion about what a "target" is, what columns ought to exist on a kanban that tracks one, and what approvals a target should cross before it is engaged.

## Targeting cycles and their stages

### Joint Targeting Cycle (JP 3-60)

JP 3-60 specifies six phases that are explicitly described as iterative rather than rigidly sequential: (1) end state and commander's objectives; (2) target development and prioritization; (3) capabilities analysis; (4) commander's decision and force assignment; (5) mission planning and force execution; and (6) assessment.[1] The cycle is the doctrinal parent of the air-tasking-order-driven JIPTL and the deliberate-targeting timeline.

### D3A (Army FM 3-60)

D3A maps cleanly onto staff cells and is the methodology Army targeting working groups actually use. Decide is the planning function where the commander identifies high-payoff targets and target selection standards; Detect is the collection function that locates the target; Deliver is the engagement function; Assess closes the loop with combat assessment and BDA.[2][3] D3A explicitly runs in parallel for many targets at any one time — different targets sit at different stages simultaneously, which is why it lends itself to a kanban representation.[3]

### F3EAD (SOF/IC)

F3EAD grew out of the counter-terrorism manhunting cycle perfected by JSOC in Iraq and Afghanistan. Find identifies a candidate using the standard intelligence questions; Fix verifies and tracks the target to a precise time/place; Finish is the kinetic or capture action; Exploit is on-site site exploitation and detainee/document/media exploitation; Analyze pulls everything captured into the picture; Disseminate spreads the resulting intelligence back into the Find phase to create the next target.[4][5] F3EAD is now also used widely in cyber threat intelligence with the same vocabulary.[18]

### Kill Chain / F2T2EA

The Air Force's kill chain — Find, Fix, Track, Target, Engage, Assess — is the dynamic-targeting expression of the joint cycle. It was proposed by then-Lt Gen John Jumper in the late 1990s with an explicit single-digit-minute response-time goal and has been adopted into both Air Force and joint doctrine.[6][7] F2T2EA is the natural vocabulary for time-sensitive targeting and counter-UAS workflows; vendors like Anduril and Palantir consistently describe their products in F2T2EA terms.[14][15]

The four cycles describe the same underlying activity at different speeds and from different perspectives. Their stage names are not synonyms but they line up roughly as shown below.

| Stage | JP 3-60 | D3A | F3EAD | F2T2EA |
|---|---|---|---|---|
| Set intent | End state and objectives | Decide | (implicit) | (implicit) |
| Build the target | Target development and prioritization | Decide | Find | Find |
| Locate | (within phase 2) | Detect | Fix | Fix / Track |
| Match capability | Capabilities analysis | Decide | (implicit) | Target |
| Authorize | Commander's decision and force assignment | (implicit, in Decide) | (implicit) | (implicit) |
| Strike | Mission planning and force execution | Deliver | Finish | Engage |
| Learn | Assessment | Assess | Exploit / Analyze / Disseminate | Assess |

## Key systems and programs

| System / program | What it does | Sponsor / service | Status | URL | Relevance to Target Workspace |
|---|---|---|---|---|---|
| Joint Targeting Toolbox (JTT) | Cross-domain targeting workflow software supporting all six phases of the joint targeting cycle; runs on NIPR/SIPR/JWICS/coalition. Legacy 5.x is being replaced by re-architected 6.x. | Air Combat Command (USAF), joint user base | Active program of record; modernization in progress | https://sam.gov/opp/8b977a9c29794533a5e5a2c0bb1dc561/view | Closest doctrinal analogue. Confirms there is appetite for a configurable, multi-domain targeting workspace but JTT is heavyweight and PoR-bound. |
| Theater Battle Management Core System (TBMCS) | Joint air-tasking-order and airspace-control-order generation; the system AOCs use to publish the ATO. | USAF (joint mandated) | Active, with TBMCS 2.0 modernization effort | https://en.wikipedia.org/wiki/Theater_Battle_Management_Core_Systems | Downstream consumer. A workspace target reaching "Deliver" should be capable of pushing a nomination toward TBMCS-equivalent ATO ingestion. |
| GCCS-J (Global Command and Control System – Joint) | Joint COP, force protection, situational awareness, and JOPES planning. | DISA / Joint Staff | Active, modernization underway | https://www.dote.osd.mil/Portals/97/pub/reports/FY2018/dod/2018gccsj.pdf | Provides the COP context targets live inside; a workspace should be able to send/receive against the COP, not replace it. |
| DCGS-A / AF DCGS / DCGS-N | Service-specific PED enterprises that ingest ISR, process imagery, exploit, and disseminate intelligence products. | Army, Air Force, Navy | Active, all in modernization | https://en.wikipedia.org/wiki/Distributed_Common_Ground_System ; https://www.af.mil/About-Us/Fact-Sheets/Display/Article/104525/air-force-distributed-common-ground-system/ | Primary upstream feeder of target data. A workspace ingest layer should be able to accept DCGS-style intel products in addition to raw CoT. |
| Maven Smart System (MSS) | Palantir-delivered CV+fusion+target-recommendation platform; descended from Project Maven; >20K users across 35 tools as of early 2026 and moving toward formal PoR status by FY26. | OUSD(I&S) / now C3BM-aligned; Palantir prime | Active, scaling rapidly; NATO MSS variant fielded | https://www.palantir.com/platforms/gotham/ ; https://defensescoop.com/2026/04/15/palantir-maven-smart-system-pentagon-program-transition-feinberg/ | Heavyweight incumbent for AI-assisted Find/Fix at the operational level. Workspace likely consumes Maven outputs rather than competes with them. |
| Palantir Gotham | Underlying data-fusion / ontology / AI-kill-chain platform on which MSS and many service implementations are built; in use by Ukraine since 2022. | Palantir (commercial) | Active, widely fielded | https://www.palantir.com/platforms/gotham/ | Establishes the de facto data model many partners use for "target object"; informs ontology design. |
| Anduril Lattice (Command & Control) | AI-powered open-architecture battle management OS integrating sensors and effectors; selected for Army IBCS-M in Nov 2025 with 4-for-4 live-fire intercept demo. | Anduril (commercial) | Active, fielded; expanding in C-UAS and air defense | https://www.anduril.com/lattice/command-and-control | Closest commercial analogue to a "pluggable workspace for kill chain"; demonstrates demand and shows where Target Workspace can differentiate (configurable workflow, lower price point). |
| Joint Fires Network (JFN) | Cross-service AI-assisted weapon-target pairing ("who should shoot who"); INDOPACOM-led prototype that transitioned to acquisition program 1 Oct 2025 under PEO C3BM. | C3BM (Air Force lead), Navy/Army/DISA | Transitioning from R&D to acquisition program of record | https://breakingdefense.com/2025/09/joint-fires-network-will-complete-transition-from-rd-to-acquisition-program-oct-1/ | Direct competitor at the "capabilities analysis / force assignment" phase. Workspace should be designed to interoperate, not collide. |
| Advanced Battle Management System (ABMS) | Air Force JADC2 contribution; connecting sensors/shooters/comms across services. | USAF | Active, multi-experiment series | https://en.wikipedia.org/wiki/Joint_All-Domain_Command_and_Control | Architecture context for any product that wants to be CJADC2-compatible. |
| Project Convergence | Army's JADC2 contribution; annual large-scale experimentation campaign focused on sensor-to-shooter. | Army Futures Command | Active, recurring | https://en.wikipedia.org/wiki/Joint_All-Domain_Command_and_Control | Useful Army venue for a workspace pilot; demonstrates Army's hunger for faster targeting tooling. |
| Project Overmatch | Navy's JADC2 contribution; data architecture for Distributed Maritime Operations. | Navy | Active, largely classified | https://en.wikipedia.org/wiki/Joint_All-Domain_Command_and_Control | Naval entry point for CoT-adjacent workflow; less public information available. |
| Global Information Dominance Experiments (GIDE) | NORTHCOM/NORAD-led series partnering with JAIC and Maven to test AI-assisted decision support across all 11 combatant commands. | NORTHCOM / NORAD / JAIC | Series of experiments since 2021 | https://www.northcom.mil/Newsroom/News/Article/Article/2702954/norad-and-us-northern-command-lead-the-third-global-information-dominance-exper/ | Demonstrated demand for cross-COCOM target-and-decision workflows; potential pilot venue. |
| TAK Server / ATAK | The de facto situational awareness ecosystem speaking CoT; ATAK is the tactical client. | DoD (TAK Product Center) | Active, widely deployed | https://takproto.readthedocs.io/en/latest/tak_protocols/ | The native integration point Target Workspace already commits to. |
| Joint Targeting School (JTS) curriculum (CJCSI 3370.01) | The training pipeline and standards for target development; defines five target types — Facility, Individual, Virtual, Equipment, Organization. | Joint Staff J2T | Active | https://irp.fas.org/doddir/dod/cjcsi3370_01.pdf ; https://www.jcs.mil/Portals/36/Documents/Doctrine/training/jts/jts_studentguide.pdf | Authoritative ontology source: target-type taxonomy, electronic target folder schema, and vetting/validation stages. |
| Collateral Damage Estimation Methodology (CDM / CDE) | Five-question, five-level methodology built on JMEM data used to estimate civilian/collateral risk before any kinetic strike. | Joint Staff (CJCSI 3160.01) | Active | https://publicintelligence.net/cjcs-collateral-damage/ | Required gate in any military targeting workflow; a workspace must be able to attach/track CDE artifacts to a target card. |

## Patterns we should consider adopting

1. **Default board templates keyed to the four doctrinal cycles.** Customers will not say "kanban columns," they will say "F3EAD board," "D3A board," "Joint Targeting Cycle board," or "F2T2EA kill-chain board." Ship those four as defaults with the column names taken verbatim from the doctrinal publications cited above.[1][2][4][6]

2. **Target type taxonomy aligned to CJCSI 3370.01.** The Joint Staff has standardized on five target types: Facility, Individual, Virtual, Equipment, Organization.[19] Use these as the first-class entity types in the data model rather than inventing new ones, so target folders can be exchanged with JTT, MSS, and Gotham consumers.

3. **Separate list views for JTL, JIPTL, RTL, NSL, and HVT/HPT.** Doctrine treats these as different kinds of list with different approval authorities; a single "backlog" view is not enough. The JIPTL has a commander's signature gate; the NSL has different ownership; the RTL imposes restrictions rather than removing the target.[16] Reflect that distinction in the UI.

4. **Approval gates as first-class workflow objects.** The Joint Targeting Cycle's Phase 4 (Commander's Decision and Force Assignment) and the CDE-gate are explicit doctrinal checkpoints, not optional metadata.[1][17] A column transition into "Deliver/Engage/Finish" should require a configurable approval artifact (rank, role, attached CDE level, ROE check).

5. **Deliberate vs. dynamic lanes.** Doctrine distinguishes deliberate targeting (days/weeks) from dynamic targeting (24-hour) with different cadence and authorities.[8] A single board with two lanes (or two linked boards) lets a unit run both without forcing them into one rhythm.

6. **Site-exploitation back-edge (F3EAD's E-A-D).** The thing that distinguishes F3EAD from earlier cycles is the explicit Exploit/Analyze/Disseminate loop that turns a finished target into the next Find.[4] The product should support a "spawn child target from finished target" action so the post-strike feedback loop is mechanical, not narrative.

7. **Multi-classification publish/subscribe.** JTT is explicitly designed to operate across NIPR/SIPR/JWICS and coalition domains.[10] Target Workspace should at minimum tag each target with a classification/releasability label and let the publish layer (CoT or otherwise) filter outputs accordingly.

8. **Open ontology and machine-readable target folder.** The DCGS Integration Backbone and Gotham/MSS both succeed largely because they impose a shared ontology that downstream consumers can rely on.[11][13] Document the target object as a versioned schema (JSON/Protobuf) from day one.

## Gaps and weaknesses

1. **Heavyweight programs of record are slow to adapt.** JTT 5.x to 6.x has been a multi-year re-architecture; TBMCS has been the air-tasking system since the 1990s and is still being "modernized."[10][9] Units consistently complain in trade press that the official tooling lags the operational tempo. This is the gap a configurable workspace can fill.

2. **Tools are organized around services, not workflows.** DCGS-A, AF DCGS, and DCGS-N are three different programs with a shared "Integration Backbone" that has historically been more aspiration than reality.[11] The same data has to be re-keyed across cells in many units.

3. **Doctrine is fuzzy about where deliberate ends and dynamic begins.** Field Artillery Association reviews note that "neither Joint nor Army doctrine draws a clear distinction between the deliberate and dynamic processes" in time-horizon terms.[8] In practice that means each unit invents its own threshold, which a configurable workspace can support but rigid tools cannot.

4. **AI components have brittle dependencies on labeled data.** The Modern War Institute analysis of AI-enabled targeting argues that advanced neural networks "require vast and labeled datasets — often unavailable in tactical contexts" and that AI should augment rather than replace targeting judgment.[20] Existing AI-targeting tools tend to over-promise machine speed and under-deliver on edge cases.

5. **Humans, not compute, are the bottleneck.** MWI and War on the Rocks both argue that the limiting factor in "machine-speed" kill chains is the human in the loop required for legal accountability — the volume of decisions does not shrink even as the per-decision time shrinks.[20][21] Tools that hide the human in the loop tend to fail audit.

6. **The CDE process is poorly digitized.** CDE methodology is rigorous and rules-based, but the actual production of a CDE pack at the unit level is still heavily manual, paperwork-heavy, and depends on classified JMEM tooling.[17] A workspace that lets a CDE pack be attached as a structured artifact (level 1-5, ROE flag, JMEM references) would already be ahead of much fielded tooling.

7. **Coalition/partner interoperability is hard.** AJP-3.9 (NATO's joint targeting doctrine) exists but cross-domain handoff between U.S. SIPR systems and coalition equivalents is a known friction point; Maven's NATO variant was explicitly created to ease this.[22] A CoT-native workspace already has an advantage here since CoT is comparatively low-classification by default.

8. **Vendor lock-in around target ontologies.** Gotham and Maven offer an opinionated ontology that customers come to depend on; switching costs are high once a unit's target folders are in Palantir's schema.[13] An open, documented schema is a real differentiator.

## Implications for Target Workspace

1. **Ship four doctrinally branded default templates out of the box** — Joint Targeting Cycle (six-phase), D3A (four-phase), F3EAD (six-phase), and F2T2EA Kill Chain (six-phase). Use the doctrinal column names verbatim. This is the single most credible signal a PM can give a targeteer that the product was built by people who read the manuals.

2. **Treat the target object as a schema, not a database table.** Adopt CJCSI 3370.01's five target types as the entity taxonomy, version the schema, and publish it. Make it round-trippable with CoT so a target card can be reduced to a CoT event and reconstituted on the far side.

3. **Make approval gates and CDE attachments first-class.** Every column transition can have an optional gate; in regulated workflows the gate is mandatory. The CDE artifact (level 1-5 plus references) should be a structured attachment, not a free-text field.

4. **Build the post-strike feedback loop into the kanban primitive.** F3EAD's edge is that exploitation feeds the next Find. A "spawn child target" action on a Finish-column card, with the parent linked, is the doctrinal feature that distinguishes this product from a generic Trello clone.

5. **Plan integrations beyond TAK in this rough priority order:** (a) DCGS-style intel ingest for upstream target data; (b) Maven/Gotham target-folder import-export for interoperability with the dominant operational AI stack; (c) JTT-style export so a developed target can be promoted into the program-of-record system at higher echelons; (d) JFN/IBCS-M-style downstream so an approved target can hand off to fires C2. CoT in/out covers the tactical edge; these cover the operational and strategic seams.

6. **Position the product as the configurable middle layer between sensors (CoT/ISR) and authoritative C2.** Anduril Lattice and Palantir Maven are billion-dollar incumbents at the high end; service tooling is rigid at the low end. The unfilled niche is a configurable workspace that any unit can stand up against its own doctrine — JSOTF running F3EAD, a Brigade running D3A, an AOC cell running F2T2EA — without buying a program of record.

## Sources

[1] https://www.justsecurity.org/wp-content/uploads/2015/06/Joint_Chiefs-Joint_Targeting_20130131.pdf
[2] https://armypubs.army.mil/epubs/DR_pubs/DR_a/ARN39048-FM_3-60-000-WEB-1.pdf
[3] https://irp.fas.org/doddir/army/atp3-60.pdf
[4] https://sofsupport.org/f3ead-sof-specific-targeting-in-the-intelligence-cycle/
[5] https://havokjournal.com/culture/tier-one-targeting-special-operations-and-the-f3ead-process/
[6] https://www.doctrine.af.mil/Portals/61/documents/AFDP_3-60/3-60-AFDP-TARGETING.pdf
[7] https://www.airandspaceforces.com/article/0700find/
[8] https://www.fieldartillery.org/news/deliberate-versus-dynamic-targeting
[9] https://en.wikipedia.org/wiki/Theater_Battle_Management_Core_Systems
[10] https://sam.gov/opp/8b977a9c29794533a5e5a2c0bb1dc561/view
[11] https://en.wikipedia.org/wiki/Distributed_Common_Ground_System
[12] https://www.dote.osd.mil/Portals/97/pub/reports/FY2018/dod/2018gccsj.pdf
[13] https://www.palantir.com/platforms/gotham/
[14] https://www.anduril.com/lattice/command-and-control
[15] https://breakingdefense.com/2025/09/joint-fires-network-will-complete-transition-from-rd-to-acquisition-program-oct-1/
[16] https://www.jcs.mil/Portals/36/Documents/Doctrine/training/jts/jts_studentguide.pdf
[17] https://publicintelligence.net/cjcs-collateral-damage/
[18] https://reliaquest.com/blog/f3ead-find-fix-finish-exploit-analyze-and-disseminate-the-alternative-intelligence-cycle/
[19] https://irp.fas.org/doddir/dod/cjcsi3370_01.pdf
[20] https://mwi.westpoint.edu/targeting-at-machine-speed-the-capabilities-and-limits-of-artificial-intelligence/
[21] https://warontherocks.com/its-about-time-the-pressing-need-to-evolve-the-kill-chain/
[22] https://nllp.jallc.nato.int/cmnt/ciedcoi/CIED%20PUBLICATIONS/Handbooks%20and%20Doctrines/AJP%203.9.%20DOCTRINE%20OF%20JOINT%20TARGETING.pdf
[23] https://defensescoop.com/2026/04/15/palantir-maven-smart-system-pentagon-program-transition-feinberg/
[24] https://www.northcom.mil/Newsroom/News/Article/Article/2702954/norad-and-us-northern-command-lead-the-third-global-information-dominance-exper/
[25] https://www.af.mil/About-Us/Fact-Sheets/Display/Article/104525/air-force-distributed-common-ground-system/
[26] https://www.congress.gov/crs_external_products/R/PDF/R46725/R46725.7.pdf
[27] https://en.wikipedia.org/wiki/Joint_All-Domain_Command_and_Control
[28] https://takproto.readthedocs.io/en/latest/tak_protocols/
[29] https://www.csis.org/analysis/pathways-implementing-comprehensive-and-collaborative-jadc2
[30] https://www.atlanticcouncil.org/in-depth-research-reports/report/how-nato-can-integrate-ai-to-prevail-in-future-algorithmic-warfare/
[31] https://en.wikipedia.org/wiki/Project_Maven
[32] https://www.airandspaceforces.com/article/winning-the-kill-chain-competition/
[33] https://en.wikipedia.org/wiki/Kill_chain_(military)
[34] https://www.mitre.org/sites/default/files/pdf/04_0962.pdf
[35] https://apps.dtic.mil/sti/tr/pdf/ADA403414.pdf
