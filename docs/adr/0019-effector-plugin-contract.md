# ADR 0019 — Effector plugin contract

Status: Accepted (ratified 2026-06-03).

> **Ratified 2026-06-03** alongside ADR 0021, whose `apply` stage dispatches effectors. Note the dispatch-semantics distinction made explicit in 0021: publishers fan out (fire-and-forget broadcast), whereas an effector *match* is a request/response query whose ranked result is recorded back to the target — not broadcast.

> Note on numbering: the original `tw-aoo` ticket called for "ADR 0014: Effector plugin contract," but `0014` shipped earlier as ICS-scope-hybrid-MVP. The Effector ADR takes the next free slot.

## Context

`docs/research/ukraine-fires-targeting.md §2` documents how Ukrainian Kropyva-style targeting software automates the *match-effector-to-target* step. A target candidate arrives (drone-classified, AI-ATR scored, OSINT-fused) and the operator needs the answer to "which weapon system, which battery, which munition?" — not just "where is it?".

Today the plugin system has two families:

- **Source** — pulls observations in (CoT, HTTP webhook, GDELT, USGS, NWS, ACLED, synthetic ATR).
- **Publisher** — fans state changes out (CoT-out, ATAK Mission Package, future webhook-out).

Effectors are a missing third role. Mechanically they *look* like Publishers — they receive a target dispatch — but their job is different: they answer a *query* with a *ranked list of options*, not broadcast a fact to everyone listening.

Lumping them into Publisher creates two visible mismatches:

1. Publishers fan out unconditionally to anyone whose column filter matches. Effectors must rank-and-return, not push.
2. Publishers have no concept of "given my inventory, which of you is the best fit?" — they're broadcasters, not match-makers.

## Decision

**Effector becomes a first-class plugin family alongside Source and Publisher.**

```python
class Effector(Protocol):
    name: str
    def match(
        self,
        *,
        target: Target,
        inventory: list[ResourceCapability],
        constraints: MatchConstraints,
    ) -> list[EffectorMatch]:
        """Return a ranked list of effector options (best first).
        Empty list means 'no eligible effector for this target'."""
```

Where:

- `ResourceCapability` describes one ICS / fires-cell asset — type (battery, drone, swift-water squad, medevac), location, status (available / committed / refit), range / endurance, payload / capability tags.
- `MatchConstraints` carries the operator-applied filters — time-on-target, weather, RoE clearance level, exclusion zones.
- `EffectorMatch` is `{ resource_id, score, rationale, eta_seconds, risk_factors[] }` so the SPA can render *why* a match was returned, not just *that* it was.

Effectors are queried, not pushed:

- The SPA opens "Match effectors" on a card → `POST /v1/effectors/match { target_id }` → server calls every enabled Effector plugin → aggregates the ranked lists → returns to client.
- The operator picks one option and drags the card through the standard approval column to dispatch. The plugin emits nothing on its own.

## Rationale

**Why distinct from Publisher.** Publishers broadcast; Effectors query. Folding them into the same protocol would force every Publisher to grow a "would you like to be queried?" mode, and every Effector to grow a "but I'm not actually broadcasting" exception. The plugin loader stays clean if the contracts are separate.

**Why not auto-engage.** This is the load-bearing decision. The Ukraine audit documents Kropyva's *ranking* role explicitly: the system does NOT auto-engage. The crew commander still confirms, the approval column still gates, the audit chain still records the human in the loop. Effectors recommend. Operators decide. Effector recommendations land on the card as a candidate set in `custom_fields.effector_candidates[]`; promotion through the approval column is what causes dispatch (via the existing Publisher plumbing if the chosen effector includes a "fires-net" Publisher in its dispatch profile).

**Why ranked list (not best single).** Givens like weather, comms windows, refit timers, and crew availability change minute-by-minute. The IC needs the top 3-5 options so they can fall through when their first choice is unavailable. A single-best API would force every change to round-trip the server.

**Audit + RoE.** Every match query is itself an audit event (`effector.matched`) carrying the target id, the inventory snapshot used, and the ranked output. This makes after-action reconstruction trivial — "at 14:32 the system was offered options X, Y, Z and the analyst chose Y" is one query. The RoE layer doesn't change: gated columns still gate, approving roles still apply.

## Out of scope (defer)

- **Inventory ground truth.** The match contract takes `inventory` as a parameter; populating it is a separate problem (Resource Roster tw-qkp is the simplest answer for SAR / disaster, formal ICS-211 + ICS-204 sync for federal). Effector plugins should not own inventory.
- **Recommendation explainability beyond `rationale: str`.** A future Effector may want to return decision-tree provenance; the protocol grows when a concrete plugin needs it.
- **Cross-instance Effector federation.** Federation slices (ADR 0016) currently transport targets and audit; carrying Effector match queries / responses across peers is post-MVP.

## Implementation pointer

The plugin loader (`src/target_workspace/plugins/loader.py`) registers Source and Publisher via separate entry points. Effector gets a third entry-point group (`target_workspace.effectors`). First reference implementation files under `tw-jt0` (or its successor).

## Consequences

- A net-new third plugin role; no breaking changes to Source / Publisher.
- The SPA grows a "Match effectors" affordance on the target detail; the recommendation list is rendered, but the human still does the move.
- The Ukraine-style fires-cell workflow becomes representable without compromising the always-gated promotion philosophy.

## Open questions deferred

- Should Effector results be cached / TTL'd, or always re-queried? (Probably re-queried — inventory is the slow-changing axis and we already memoize that elsewhere.)
- A Publisher can be a downstream side-effect of an Effector dispatch decision; how does the SPA discover which Publisher pair belongs to which Effector recommendation? Likely via Effector-declared `dispatch_via: <publisher_name>` field in the EffectorMatch — implementation detail when the first real plugin lands.
