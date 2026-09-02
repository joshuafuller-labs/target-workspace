# ADR 0021 — Workflow autonomy via a Signal → Policy → Decision → apply pipeline

**Status:** Accepted
**Date:** 2026-06-03 (ratified 2026-06-03)

**Ratification note.** Four forks raised during review are resolved and folded into the text below: (1) **policy composition adopted** — boards host an ordered set reduced by the `DENY > PROPOSE > ALLOW` safety lattice, with `ABSTAIN` added to `Decision` now because it is the frozen third-party contract; (2) **Signal is closed-core + open `external:<ns>` envelope** — the CoT fixed-schema-plus-`<detail>` idiom — as the sole third-party signal door; (3) **topology (`board.can_move`) stays a hard gate** a policy may narrow but never widen; (4) **temporal interval-time (`valid_from`/`valid_to` + `WindowOpened`/`Closed`) is carried now** so the future timeline view (ADR 0022) never reopens this contract.

## Context

Cards move between board columns. Today every move is manual and that works perfectly. We almost certainly want optional autonomy later — a card that promotes itself when an assigned callsign arrives on-scene (`tw-d3t9`), when a fused observation crosses a confidence threshold, or when an SLA timer expires. The question this ADR settles is **how** autonomy enters the system, so that adding it later is a plug-in, not a rewrite.

The current implementation has the right instincts but an incomplete seam:

1. **Single chokepoint, but it fuses two concerns.** `workflow/engine.py::transition_target` is the one path every move takes — good. But it *decides* (calls `board.can_move`, checks `requires_approval`) and *applies* (persists the move, writes the signed audit event, dispatches publishers) in the same function body. Decide-and-apply are welded together.

2. **The policy seam is nominal, not load-bearing.** `models/promotion_policy.py` defines a fully-validated `PromotionPolicy` (modes `gated` / `conditional` / `autonomous`, `min_confidence`, `auto_publish_column_id`, …). **The engine never reads it.** The contract `contracts/promotion_policy.py` is a Protocol with a single `name` attribute and no decision method. The autonomy spectrum is declared as data with no code that consumes it.

3. **Two competing autonomy mechanisms are forming.** Independently of `PromotionPolicy`, `api/workflow_triggers.py::consider_actions` is a presence-driven rule evaluator with its own grammar (`min_assignees:N`, `all_assigned`, `any`). It is — correctly — a *pure function that returns proposed actions for the caller to apply*. But it is a second decision surface with a different vocabulary, different storage, and a different audit shape from `PromotionPolicy`. If both grow, they diverge into two rule engines.

4. **The actor is assumed human.** `models/audit_event.py` types the actor as `actor_id: UUID  # User who caused this event.` An autonomous mover has no identity in the audit chain. "AI proposes, human decides" (DoDD 3000.09, and the Maven Target Workbench pattern our research validates) requires the audit to *distinguish* an AI-proposed move from a human-approved one. A borrowed human UUID or a magic "system" user destroys that distinction — and the signed audit chain is our load-bearing differentiator.

5. **There is no first-class "proposed move."** A move either happens (manual) or is blocked (`requires_approval` + missing `approving_role`). There is no object representing *"the system wants to move this card; here is the evidence; a human must confirm."* That object is the center of any human-in-the-loop autonomy, and it does not exist (grep for `nominat`/`proposed`/`pending_move` is clean).

The cost asymmetry is the whole reason to decide now. Today: one manual path and one already-pure trigger function — cheap to unify. Later: autonomy bolted into `transition_target` as `if mode == ...` branches, two rule engines diverged, an audit chain that cannot name a non-human actor, and no way to preview what autonomy *would* do — so it can never be safely switched on in a real deployment. That is the rewrite this ADR exists to prevent.

## Decision

Every column move — manual or autonomous, now and forever — flows through one pipeline:

```
Signal  →  Policy.evaluate()  →  Decision  →  apply()
(input)     (pure, no effects)   (data)       (only side-effects live here)
```

### 1. Signal — the unifying input

A move is never requested directly. Something *emits a signal*, and the pipeline reacts. The pivotal consequence: **a manual click is just a signal**, so the manual path and every future autonomous path are the *same code*, differing only in who emits.

**Every signal shares one envelope** (frozen — this is a third-party contract, see §7):

```
Signal:
  kind:        str            # a core enum value, OR "external:<namespace>.<name>"
  emitted_by:  Principal      # who/what raised it
  target_id:   UUID | None    # subject; None for board-level signals
  occurred_at: datetime       # when the fact became true (injected clock, ADR 0010)
  valid_from:  datetime | None  # interval facts (windows); defaults to occurred_at
  valid_to:    datetime | None  # interval facts; None = instantaneous / open-ended
  payload:     dict           # kind-specific evidence
```

**Closed core, open edge.** The *core* `kind`s are a closed, versioned enum, so bundled policies are statically typed and the pipeline can reason about them. Third parties do **not** invent core kinds; they emit `external:<namespace>` signals carrying an opaque payload, and custom policies match on that. This is deliberately the same shape as CoT itself — a fixed schema with an open `<detail>` extension — which is the right idiom for a CoT-native product. The envelope and the `external:` convention are frozen alongside `evaluate`.

Core taxonomy (additive — new core kinds never break existing ones):

| Signal | Emitted by | Carries | Time |
|---|---|---|---|
| `MoveRequested` | operator (UI/API) | requesting user, to_column, justification | instant |
| `PresenceArrived` / `PresenceDeparted` | geofence engine | callsign, geo-attestation (lat/lon/source/CE/radius) | instant |
| `ObservationFused` | Source plugin / ATR | new confidence, source chain | instant |
| `WindowOpened` / `WindowClosed` | scheduler | window id, kind (e.g. ISR collection) | **interval** |
| `DwellElapsed` | scheduler | column, duration (SLA timer) | instant (fires at deadline) |
| `NominationApproved` / `NominationRejected` | operator | nomination id, resolving user | instant |
| `external:*` | third-party plugin | namespaced opaque payload | per-emitter |

**Temporal facts are first-class, not bolted on.** `WindowOpened`/`WindowClosed` and the `valid_from`/`valid_to` interval exist because some facts are *anticipated*, not reactive — an ISR collection window, a planned on-scene ETA, an SLA deadline are known *now* to hold over a *future* interval. The scheduler stores the interval fact and emits the boundary signals as the injected clock reaches them. This is the hook a future timeline/Gantt view hangs on (see the closing note); we are not designing that view here, but the Signal contract can carry interval-time so it never has to reopen.

### 2. Policy — pure evaluation, the frozen third-party contract

```python
class PromotionPolicy(Protocol):
    name: str
    def evaluate(self, signal: Signal, ctx: DecisionContext) -> Decision: ...
```

`evaluate` is **pure**: it may *read* board topology, target state, the PLI cache, confidence — all via `ctx` — and may **not** mutate anything. `DecisionContext` is a read-only view.

Two kinds of rule live behind this one surface, and the distinction is deliberate:
- **Topology** — `board.can_move(from, to)` — is a structural invariant: what moves are *possible*. Always enforced first; an illegal move is `DENY` regardless of policy.
- **Policy** — what is *permitted right now* among the legal moves. This is where `gated` / `conditional` / `autonomous` live.

The three `PromotionPolicy` modes become three bundled policies, not engine branches:
- `gated` → every required-stage move returns `PROPOSE` (human must approve).
- `conditional` → `ALLOW` if confidence ≥ `min_confidence`, else `PROPOSE` or route to `on_low_confidence_route_to_column_id`.
- `autonomous` → `ALLOW` straight to `auto_publish_column_id`.

`workflow_triggers.py::consider_actions` collapses into a built-in presence policy consuming `PresenceArrived`. Its grammar survives as that policy's config; it stops being a parallel engine.

### 3. Decision — verdict as data, divorced from its application

```python
Decision = ALLOW | DENY | PROPOSE(approver_role) | ABSTAIN
           + reason: str
           + evidence: dict           # attestation, confidence, source chain
           + proposed_by: Principal    # who/what wants this move
           + target_id, to_column_id
```

`ABSTAIN` means *"this policy has no opinion on this signal"*, so a board can host many narrow, single-concern policies without each being forced to a verdict (see §7). A `Decision` is inert. This single split — verdict separated from effect — is what unlocks the four capabilities we cannot get today:
- **Dry-run.** Run `evaluate` without `apply` and return the `Decision`. This is how an operator safely enables autonomy: preview what it *would* do across a whole board before turning it on.
- **Approval queue.** `PROPOSE` writes a Nomination instead of moving the card.
- **Denied-move audit.** `DENY` can be recorded for tuning, not silently dropped.
- **Side-effect-free policy tests.** Assert on `Decision` objects; no DB, no publishers.

### 4. Principal — typed actor, signable, non-human-aware

```python
Principal = HumanUser | ServiceAccount | PolicyAgent | SourcePlugin
            (id, kind, display_name, signing_identity)
```

The audit event's actor becomes a `Principal` reference carrying a `kind`, not a bare user UUID. Each kind has its own signing identity, so *"presence policy `pp-geofence` moved this card on attestation 34.05/-118.24"* is a first-class, **signed** statement — attributable, non-repudiable, and clearly *not* a human decision. Backward-compatible: today's `actor_id` maps to `kind = HumanUser`.

### 5. Nomination — the first-class proposed move

When `evaluate` returns `PROPOSE`, `apply` does **not** touch the card. It writes a `Nomination`:

```
Nomination(target, from_column, to_column, proposed_by: Principal,
           evidence, created_at, status: pending|approved|rejected|expired,
           resolved_by: Principal | None)
```

Approval is not a special path — it is a `NominationApproved` signal that re-enters the same pipeline and yields an `ALLOW`. The approval queue *is* the set of pending nominations. `tw-d3t9` will need this object regardless; we design it deliberately rather than discover it.

### 6. apply — the only place side-effects live

`apply(decision)` is the sole mutator:
- `ALLOW` → persist move (version-bump), write signed audit (`actor = decision.proposed_by`), then dispatch outputs. **Two dispatch semantics, not one:** *publishers* fan out fire-and-forget (broadcast a fact to anyone whose column filter matches; failures are non-fatal); *effectors* (ADR 0019) are request/response — a `match` query returns a ranked option list that `apply` **awaits and records back onto the target**, never broadcasts. An effector is not a fire-and-forget side effect.
- `PROPOSE` → write `Nomination`, write signed audit `nominated`, notify approver role. **No card move.**
- `DENY` → optionally write signed audit `move_denied`. No card move.

### 7. Composition — many narrow policies, one safety lattice

A board carries an **ordered set** of policies, not one. Real boards mix concerns — "presence promotes" *and* "confidence gates the FINISH stage" *and* "a human approves CLOSED" are three separate, swappable policies, not one god-policy (a god-policy would violate ADR 0008's malleability principle). Each policy `ABSTAIN`s on signals it doesn't care about.

The pipeline reduces every applicable policy's `Decision` through a fixed **safety lattice**:

```
DENY  >  PROPOSE  >  ALLOW          (ABSTAIN ignored)
```

Reduction is **per candidate destination**, not global — a signal may yield proposals to several `to_column_id`s, and the lattice reduces the verdicts *within each destination*:

- Within a destination, any `DENY` ⇒ that destination is `DENY` (vetoed). A veto removes *that move*; it does **not** freeze other legitimate moves.
- Else any `PROPOSE` ⇒ that destination is `PROPOSE`.
- A destination is `ALLOW` only if every non-abstaining policy allows it.

Then **across** the surviving destinations: if exactly one resolves to `ALLOW`, apply it; if two or more survive as `ALLOW`, that ambiguity is escalated to `PROPOSE` (conflicting autonomous moves mean the system is not confident, so it asks a human rather than picking arbitrarily); if none is `ALLOW`, the strongest remaining verdict stands (`PROPOSE` if any destination proposes, else no-op).

The lattice is **commutative and monotonic toward caution**: adding a policy can only make a destination *more* conservative, never less. That property is the safety argument handed to a compliance reviewer — a new policy cannot silently *widen* what autonomy will do.

This forces `ABSTAIN` into the `Decision` type **now**: `Decision` is the frozen third-party contract, so adding `ABSTAIN` later would break every existing policy. The reducer is ~a dozen lines; deferring it is the expensive option.

### Concrete rules

- **No side door.** Every move enters through a `Signal`; `transition_target`'s public behavior is preserved but its body splits into `evaluate` + `apply`. Nothing mutates a card outside `apply`.
- **Decide is pure.** A policy that mutates state is a conformance-test failure (per ADR 0005's `tests/contract/` harness).
- **Topology before policy.** `board.can_move` is checked first, always; policy chooses only among legal moves.
- **Actors are typed.** Autonomous moves are attributable to a named non-human `Principal` with its own signing identity. No magic "system" user.
- **PROPOSE never moves a card.** It writes a `Nomination`.
- **The Protocol signature is frozen** at `evaluate(signal, ctx) -> Decision`. That is the contract third-party policies (`target_workspace.policies` entry-point, ADR 0005) compile against; it must not churn. `Decision` includes `ABSTAIN` from day one.
- **Boards host an ordered set of policies**, reduced by the `DENY > PROPOSE > ALLOW` lattice (`ABSTAIN` ignored). A policy may narrow the legal-move set, never widen it.
- **Core `Signal` kinds are a closed, versioned enum.** Third parties emit `external:<namespace>` signals and match them in custom policies. The Signal envelope and the `external:` convention are frozen with `evaluate`.
- **Signals carry interval time** (`valid_from` / `valid_to`); the scheduler is the emitter of anticipated and boundary signals.
- **Dry-run is a prerequisite for autonomy.** No deployment may enable a non-`gated` policy without a preview path that runs `evaluate` and shows the `Decision` set without applying.

## Alternatives considered

- **A — Mode branches inside `transition_target`.** Add `if policy.mode == "conditional": ...` to the existing function. Rejected: re-welds decide to apply, makes dry-run impossible, leaves the audit actor human-only, and grows untestable without a DB.
- **B — Keep both engines (`PromotionPolicy` *and* `WorkflowTriggerRule`).** Rejected: two grammars, two storages, two audit shapes that drift apart; doubles the plugin surface third parties must learn.
- **C — Adopt an external workflow/BPMN engine (Temporal, Camunda, …).** Rejected: violates the single-container hobbyist default (ADR 0008 — must run on a Pi with one `docker run`), introduces an opaque audit path that competes with our signed chain, and is far heavier than the problem.
- **D — This ADR: one unified `Signal → Decision → apply` pipeline.** Chosen.

## Consequences

**Wins:**
- Manual and autonomous moves are one code path; autonomy ships as policies + signal sources with **zero change to `apply`**.
- The signed audit chain can finally name *what* moved a card and *on what evidence* — strengthening the differentiator instead of eroding it.
- Dry-run makes autonomy *operationally* adoptable: you can see what it would do before trusting it. Without this, no responsible operator turns autonomy on.
- HITL ("AI proposes, human decides") is structural, not bolted-on — aligns with DoDD 3000.09 and the Maven pattern our research validates, and reduces compliance objections in the LE and DoD go-to-markets.
- The two nascent rule engines collapse into one surface third parties learn once.
- The refactor pays for itself **even if autonomy never ships**: dry-run, denied-move audit, and side-effect-free policy tests all improve the manual product today.

**Trade-offs accepted:**
- A refactor with **zero user-visible change** — hard to justify to feature-counting, justified entirely by upgradeability and audit integrity. Done under TDD (ADR 0006), manual behavior is pinned by tests first.
- More ceremony for the simple manual case (signal → evaluate → apply instead of a direct call). **Mitigation:** a thin `MoveRequested` signal and an `ALLOW` fast-path keep the common case cheap.
- The `Principal` model touches the audit schema (a migration). **Mitigation:** additive `actor_kind` column; existing rows backfill to `HumanUser`; the signed-event format gains a field rather than changing shape.
- `Nomination` is new state with a lifecycle (expiry, queue). Accepted: it is required for any HITL autonomy regardless of design.
- Policy **composition** (ordered set + reducer + `ABSTAIN`) is more than a single-policy engine. **Mitigation:** `ABSTAIN` must live in the frozen `Decision` contract *now* regardless — retrofitting it is a breaking change to every third-party policy — so the reducer is the cheap half of a decision we cannot defer anyway.
- A first-class **temporal/interval** dimension on every signal is carried even by deployments that never schedule a window. **Mitigation:** the fields are nullable and default to `occurred_at`; the cost is two columns, and it buys the timeline view (and SLA/dwell autonomy) without a later contract break.
- Risk of designing for autonomy that may never land. **Mitigation:** see the final "win" — the split is net-positive for the manual-only product on its own, so the bet is asymmetric.

## References

- [ADR 0008 — Malleability is the product's load-bearing principle](0008-malleability-principle.md) — this pipeline is how the autonomy axis stays data-driven
- [ADR 0005 — Plugin discovery via entry-points](0005-plugin-system-entry-points.md) — `target_workspace.policies` group; `evaluate` is the frozen contract
- [ADR 0006 — TDD and the supply-chain bar](0006-tdd-and-supply-chain-bar.md) — the refactor is red-green-refactor, manual behavior pinned first
- [ADR 0019 — Effector plugin contract](0019-effector-plugin-contract.md) — effector dispatch is an `apply`-stage side-effect
- `src/target_workspace/workflow/engine.py` — `transition_target` splits into `evaluate` + `apply`
- `src/target_workspace/contracts/promotion_policy.py` — gains the `evaluate(signal, ctx) -> Decision` method
- `src/target_workspace/api/workflow_triggers.py` — `consider_actions` becomes a built-in presence policy
- `src/target_workspace/models/audit_event.py` — actor becomes a typed `Principal`
- DoDD 3000.09 — "human-in-the-loop semi-autonomous"; `docs/research/SYNTHESIS.md` — Maven "AI proposes, human decides"
- Roadmap: `tw-d3t9` (PLI ↔ workflow auto-apply) is the first consumer of this pipeline

## Note — temporal awareness (timeline / Gantt) is a deferred consumer

A timeline/Gantt view of board events — the situational-awareness surface a Battle Captain, a SAR planner, or an ISR scheduler needs to see *when* things happened and *when* they are planned — is **out of scope for this ADR but is the reason the Signal envelope carries interval time**. Designed correctly, that view is a read-model projection: the past is the signed audit stream, the present/future is the set of open `WindowOpened`/`WindowClosed` intervals plus pending `Nomination` expiries. Capturing `valid_from`/`valid_to` and the scheduler-emitted boundary signals *now* means the timeline never forces a change to the workflow contract. The view itself — lanes, granularity, interaction — is deferred to its own ADR (candidate **0022**).
