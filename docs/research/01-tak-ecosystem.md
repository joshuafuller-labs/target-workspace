# TAK Ecosystem Prior Art

## Landscape overview

The Team Awareness Kit (TAK) ecosystem is a family of geospatial situational-awareness clients, servers, and protocols that originated inside the U.S. Air Force Research Laboratory and was open-sourced for civilian use as ATAK-CIV in 2020 [1][2]. The core data exchange format is Cursor on Target (CoT), an XML schema originally specified at MITRE; later versions of the TAK suite added a Protobuf wire format ("TAK Protocol Version 1") for mesh and low-bandwidth use [3][4]. CoT messages use a hyphenated type tree where the `atoms` branch maps directly to MIL-STD-2525B symbology, so any "target" in the ecosystem is fundamentally a CoT event with an affiliation (friendly, hostile, neutral, unknown) and a battle-dimension code [3]. Around this core sit clients — ATAK (Android), iTAK (iOS), WinTAK (Windows), WebTAK, TAK Tracker (send-only Android), and TAK Aware (third-party iOS) — and a growing set of servers: the official TAK-Product-Center Server (GPL Java) [5], OpenTAKServer / OTS (Python, MIT) [7], and Taky (hobby Python, MIT) [8].

Most "workflow" in this ecosystem today happens implicitly in the map view: an operator drops a marker, types it as hostile, optionally attaches a 9-line or sensor-point-of-interest, and the CoT propagates to every subscribed client through the TAK Server messaging service [9][10]. Persistence and grouping happen through the **Mission API** — a Marti REST endpoint set under `/Marti/api/missions/<name>` that lets clients create a named "mission," subscribe to it with roles (`MISSION_OWNER`, `MISSION_SUBSCRIBER`, `MISSION_READONLY_SUBSCRIBER`), attach CoT events and files, and receive deltas via Data Sync [11][12]. The Mission API is the closest thing in stock TAK to a "board" abstraction, but it is a flat list of items, not a column-based or state-based view.

Plugin development is concentrated in three layers: ATAK/WinTAK client plugins (Java + ATAK SDK on Android, MEF/.NET on Windows) [13][14], TAK Server "MessageInterceptor" and submit plugins compiled as Java JARs into the `tak.server.plugins` package [15], and OTS server plugins (Python Flask Blueprints) [7][16]. Commercial plugin builders include PAR Government (Push-for-TAK, Point Mensuration Tool, Quick Chat) [17], CloudRF (SOOTHSAYER) [18], goTenna (mesh radio) [19], and various integrators. Target-relevant workflow exists in narrow slices — Fire Tools / 9-line / Target Manager built into ATAK, the Point Mensuration Tool for coordinate refinement, and the externally hosted Palantir Target Workbench that bridges to TAK via Lattice for division-level targeting [20] — but there is no general-purpose, configurable kanban or staged-workflow tool over CoT in any open or commercial inventory I could verify.

## Key players and projects

| Name | What it is | Status | URL | Why it matters to Target Workspace |
|---|---|---|---|---|
| TAK Server (official) | Java/Spring server from TAK Product Center; reference Marti REST + Mission API + plugin manager | Active, OSS (GPL) | https://github.com/TAK-Product-Center/Server [5] | Defines the Mission API and plugin contract we must integrate with as a publisher target |
| OpenTAKServer (OTS) | Newer Python Flask server with Plugin Update Server, Mission API, Flask Blueprint plugin SDK, public repo at repo.opentakserver.io | Active, OSS | https://github.com/brian7704/OpenTAKServer [7] | Best documented plugin SDK in the ecosystem; their Flask-Blueprint pattern is the closest model to what Target Workspace would expose |
| Taky | Hobby Python TAK server, ~240 stars | Maintained but explicitly experimental (TRL 5-6) | https://github.com/tkuester/taky [8] | Useful as a minimal CoT reference implementation; not a serious production target |
| CloudTAK | DFPC-COE browser COP with ETL infrastructure for non-TAK sources; AGPL | Active, OSS | https://github.com/dfpc-coe/CloudTAK [21] | Closest adjacent pattern: pluggable ETL ingesting non-CoT data and emitting to TAK Server. Has open bugs around Mission vs. raw-CoT destination routing [22] |
| node-CoT (@tak-ps/node-cot) | TypeScript CoT library: XML/Protobuf <-> JS object <-> GeoJSON, basemap and data-package types | Active, OSS (MIT), latest v14.x May 2026 | https://github.com/dfpc-coe/node-CoT [23] | Production-grade JS/TS CoT primitive; would be the right base if Target Workspace is built in Node |
| node-tak | TypeScript SDK for TAK Server TLS streaming + REST; CLI included | Active, OSS (MIT), latest v12.x May 2026 | https://github.com/dfpc-coe/node-tak [24] | Drop-in publisher client for any Node-based Target Workspace backend |
| PyTAK | Python `QueueWorker` / `CLITool` framework for CoT clients, gateways, servers; supports TLS, multicast, file, stdout, enrollment URLs | Active, OSS (Apache-2.0) | https://github.com/snstac/pytak [25] | Battle-tested asyncio producer/consumer abstraction we can mirror in any Source/Publisher SDK |
| takproto | Python encoder/decoder for TAK Protocol v0 (XML) and v1 (Protobuf) | Active, OSS | https://pypi.org/project/takproto/ [26] | Required dependency to write Protobuf-speaking publishers (TAK Tracker, ATAK Mesh SA) |
| TAK Aware | Third-party iOS TAK client + SwiftTAK Swift Package, Flight Tactics | Active, OSS | https://github.com/flighttactics/TAKAware [27] | Demonstrates that an alternative client can be built outside the TPC stack; relevant if we ever want to ingest from non-TAK iOS sources |
| TAK Tracker | Official "send only" Android app, no map | Active, official | https://play.google.com/store/apps/details?id=gov.tak.taktracker [28] | A real source of position-only CoT; not a workflow tool |
| ExCheck (ATAK/WinTAK plugin) | Shared template-based checklist hosted on the TAK Server; tasks can be set pending/complete with notes; needs TAK Server >= 1.3.3 | Maintained (in TAK Server WebUI 1.5+) | (no public TPC doc URL; see TAK Server release notes) | The only stock "stateful list of tasks shared over CoT" capability — closest thing to a board, but flat and template-locked |
| Point Mensuration Tool (PAR) | ATAK/WinTAK plugin guiding a workflow to extract mensurated coordinates from imagery for precision fires | Active, government distribution via TAK.gov | https://blog.pargovernment.com/push-for-tak/point-mensuration-tool [17] | Existence proof of a stepped, plugin-driven workflow in TAK — single-purpose, not configurable |
| tak-gpt (Raytheon BBN) | Server-side TAK plugin that exposes LLM agents (Ollama, OpenAI, Anthropic, Vertex) as TAK contacts; Java JAR loaded by TAK Server Plugin Manager | Active, OSS | https://github.com/raytheonbbn/tak-gpt [30] | Proves the "server-side plugin appears as a CoT contact" pattern that Target Workspace could use to expose itself inside ATAK |
| Anduril Lattice + Palantir Target Workbench | Closed commercial targeting platform that bridges into TAK; demonstrated division-level targeting in joint exercises | Active, closed | https://defensescoop.com/2025/05/07/anduril-palantir-partnership-menace-edge-software/ [20] | Direct workflow competitor at the high end; classified/proprietary, expensive — leaves a real gap below it |

(A longer community pick-list — atak-forwarder, OpenTakNavigation, APRS-TAK, CotMaker, adsbcot, aprscot, Hammer/ARIK, Meshtastic ATAK Plugin, CloudRF SOOTHSAYER — is catalogued in [31], but none of these address target workflow.)

## Patterns we should consider adopting

**1. PyTAK-style `QueueWorker` producer/consumer abstraction.** PyTAK exposes a small surface area — extend `QueueWorker`, push CoT objects into an asyncio queue, let the framework handle TLS, certs, multicast, and reconnection [25]. This is the de facto pattern any Python developer in this ecosystem already knows. A Target Workspace Source SDK that looks the same will have near-zero onboarding cost. Mirror the equivalent in TypeScript on top of `node-CoT` + `node-tak` [23][24].

**2. Flask Blueprint plugins with declared config schema (OpenTAKServer model).** OTS plugins subclass `Plugin`, register API routes with `@auth_required` / `@roles_accepted` decorators, declare validated config options, and optionally ship a Mantine/React iframe UI from a separate repo. Background work runs in an `activate()` method [16]. This is the cleanest separation of plugin code, plugin config, and plugin UI in the TAK world and we should copy it almost verbatim for our Source and Publisher adapter SDK.

**3. Plugin update server with versioned APKs (ATAK 5.5 mechanism).** Starting with ATAK 5.5, clients query the server for a per-version plugin manifest; the server returns the right APK [33]. If Target Workspace publishes ATAK side-companions (e.g. a "review-this-target" widget), we should ship them through OTS's update server contract rather than rolling our own distribution.

**4. TAK Server MessageInterceptor pattern for state transitions.** TAK Server lets a Java plugin sit between incoming CoT and outbound broadcast [15]. We can model column transitions in Target Workspace as a MessageInterceptor that watches for marker updates, applies workspace rules, and emits a derived CoT (e.g., updated affiliation or new mission destination) without touching the client. This avoids forking every ATAK install.

**5. Mission API for grouping, role, and delta sync.** The Mission API already supports named missions, three subscriber roles, and pushes changes to subscribed clients [11][12]. A kanban column maps cleanly to a mission; moving a card from column A to column B becomes a "remove from mission A, add to mission B" sequence. We get persistence, RBAC, and client-side delta sync for free. The known CloudTAK bug [22] is a warning to actually exercise the `addDest` path during testing.

**6. CoT type tree as the schema bridge to MIL-STD-2525.** Because the type field encodes affiliation and battle dimension [3], a workspace column transition can be expressed as a type-prefix rule ("anything with `a-h-*` moves to triage column"). Lean on the type tree instead of inventing a parallel taxonomy.

**7. tak-gpt-style "plugin appears as a contact" pattern.** Raytheon BBN's TAK-GPT registers as a normal TAK contact and chats back through standard CoT channels [30]. Target Workspace could expose itself as a "Workspace Bot" contact that responds to operator actions (e.g., chat `nominate THIS`) — instantly usable from any unmodified ATAK/iTAK/WinTAK client.

**8. Node-CoT GeoJSON bridge.** node-CoT does bidirectional CoT <-> GeoJSON conversion [23]. Adopting GeoJSON as Target Workspace's internal representation keeps the door open for non-TAK publishers (Esri, MapLibre, OGC API Features) without re-modeling.

## Gaps and weaknesses

**1. No configurable, stateful workflow over CoT.** ExCheck is the only shared-state collaboration plugin in the stock suite, and it is template-locked checklists — not user-defined columns, not per-target state machines, no transitions. The CivTAK community plugin inventory explicitly contains no kanban, project-management, or workflow-automation plugins [31].

**2. Mission API is a list, not a board.** Missions group CoT events but have no concept of ordering within the group, no "stage" or "column" attribute, no transition events, and no audit trail of who moved what when. CloudTAK's experience shows mission routing itself is fragile in practice [22].

**3. Source-adapter sprawl with no shared SDK.** Each "X to CoT" bridge (adsbcot, aprscot, etc.) is built independently on top of PyTAK or raw sockets. There is no published Source/Publisher adapter abstraction shared across the ecosystem — every integrator reinvents the queue, retry, and cert handling.

**4. Audit, provenance, and chain-of-custody are essentially absent.** CoT events have a UID and a stale time, but there is no first-class record of "this target was nominated by sensor X at T0, reviewed by analyst Y at T1, approved by commander Z at T2." Mission API logs file uploads but not state transitions. For any approval workflow this is disqualifying out of the box.

**5. Plugin distribution is bifurcated and friction-heavy.** Official plugins live behind tak.gov click-through agreements [34][35]; community plugins live across GitHub, repo.opentakserver.io [7], and ad-hoc APKs. There is no unified marketplace. A new vendor has to publish through both channels to get reach.

**6. Commercial high-end (Palantir TWB + Anduril Lattice) is closed and expensive.** Division-level targeting on TWB/Lattice has been publicly demonstrated [20], but it is a top-down enterprise procurement, not something a battalion S2 can stand up on a TAK Server next Tuesday. Nothing fills the middle.

**7. Sparse server-side plugin documentation in the official server.** TAK-Product-Center/Server has a plugin manager microservice and a `tak.server.plugins` Java package convention, but third-party guides note the SDK documentation is thin and the licensing on the repo files is unclear ("Unknown" on LICENSE.md per GitHub's auto-detection) [5][15]. OTS's docs are significantly better than the official server's docs for plugin authors [16].

**8. CoT semantics for "lead vs. confirmed target vs. nominated target" are conventional, not standardized.** Operators use callsigns and remarks fields to indicate stage today; nothing in the CoT type tree distinguishes a "lead" from a "nominated target" from an "approved target." Any workflow tool has to choose: extend type, add a `<detail>` sub-element, or layer state externally.

## Implications for Target Workspace

**1. Adopt the Mission API as the persistence and broadcast backbone for columns.** One mission per column, with the workspace orchestrator handling cross-mission transitions. This buys delta sync to clients and RBAC for free, avoids forking ATAK, and matches the strongest stateful pattern stock TAK already offers [11][12]. Validate the `addDest` routing path early to avoid the CloudTAK bug class [22].

**2. Ship a polyglot Source/Publisher SDK with two reference implementations: Python (PyTAK-shaped) and TypeScript (node-CoT / node-tak-shaped).** These are the two languages where 95% of CoT bridges actually live. The OTS Flask-Blueprint plugin shape is the right structural template for both [16][25]. Declare config schemas so plugins can be configured from the workspace UI without code.

**3. Make state transitions first-class CoT-native events, not opaque internal records.** Every column move should emit a CoT (likely a custom `<detail>` element under a configurable type prefix, plus a Mission API mission-change), so downstream consumers — TAK Server, OTS, anything subscribed — see the workflow as native traffic, not as out-of-band metadata. This is the gap that Mission API does not fill [11].

**4. Position against ExCheck, not against Palantir TWB.** ExCheck is the de facto workflow tool; it is template-locked, flat, and lives only inside the map client. Target Workspace as "configurable, stage-based ExCheck with pluggable sources/sinks" is a defensible, plain-English positioning that battalion-level customers will understand. Going head-on against TWB invites comparisons we cannot win on integration breadth.

**5. Build chain-of-custody as a core feature, not a plugin.** Because nothing in the ecosystem does this well, append-only state-transition logging signed by operator identity is a real competitive moat for any government customer. Make it queryable through the same REST surface as the board.

**6. Publish Target Workspace itself as a TAK Server-side plugin pattern (tak-gpt style).** A "Workspace" CoT contact that appears in any ATAK/iTAK/WinTAK client gives instant zero-install usability for end-users [30]. The full kanban lives in a browser UI (CloudTAK-style [21]); the contact is the in-map control surface.

## Sources

[1] https://en.wikipedia.org/wiki/Android_Team_Awareness_Kit
[2] https://hackaday.com/2022/09/08/the-tak-ecosystem-military-coordination-goes-open-source/
[3] https://github.com/dB-SPL/cot-types
[4] https://takproto.readthedocs.io/en/latest/tak_protocols/
[5] https://github.com/TAK-Product-Center/Server
[7] https://github.com/brian7704/OpenTAKServer
[8] https://github.com/tkuester/taky
[9] https://docs.tak.gov/api/takserver
[10] https://www.gofferje.net/it-stuff/tak-mission-api-1/
[11] https://docs.opentakserver.io/mission_api.html
[12] https://docs.opentakserver.io/marti_api.html
[13] https://www.riis.com/blog/plugins-with-atak-civ-sdk-5-5
[14] https://www.riis.com/blog/introduction-to-wintak
[15] https://www.riis.com/blog/atak-plugins-2-the-tak-server
[16] https://docs.opentakserver.io/plugins.html
[17] https://blog.pargovernment.com/push-for-tak/point-mensuration-tool
[18] https://github.com/Cloud-RF/SOOTHSAYER-ATAK-plugin
[19] https://gotennapro.com/pages/tech-partners-atak
[20] https://defensescoop.com/2025/05/07/anduril-palantir-partnership-menace-edge-software/
[21] https://github.com/dfpc-coe/CloudTAK
[22] https://github.com/dfpc-coe/CloudTAK/issues/1160
[23] https://github.com/dfpc-coe/node-CoT
[24] https://github.com/dfpc-coe/node-tak
[25] https://github.com/snstac/pytak
[26] https://pypi.org/project/takproto/
[27] https://github.com/flighttactics/TAKAware
[28] https://play.google.com/store/apps/details?id=gov.tak.taktracker
[30] https://github.com/raytheonbbn/tak-gpt
[31] https://www.civtak.org/tag/plugins/
[33] https://docs.opentakserver.io/update_server.html
[34] https://tak.gov/pages/our-process
[35] https://www.civtak.org/2022/04/28/tpc-new-plugins/
