# ADR 0022 — Board temporal awareness: the timeline (Gantt) view

**Status:** Accepted
**Date:** 2026-06-03

## Context

A board today offers two situational-awareness surfaces: the **map** (where things are) and the **kanban** (what state things are in). It has no **temporal** surface — *when* things happened and *when* things are planned. For the roles this product serves, that missing axis is a real gap in awareness, not a nicety:

- A **Battle Captain** runs a battle rhythm — collection windows, shift changes, planned actions — and needs to see the next few hours laid out, not just the current board state.
- A **SAR planner** sequences search assignments against daylight, tides, and team endurance.
- An **ISR scheduler** lives and dies by collection windows opening and closing.

Without a timeline, you see only the present slice; you cannot see that a card has been stuck in one column for six hours, that an ISR window closes in twenty minutes, or that two planned actions collide. ADR 0021 deliberately gave every `Signal` interval-time (`valid_from`/`valid_to`) and added `WindowOpened`/`WindowClosed` signals *specifically so this view could exist as a read-model*, without reopening the workflow contract. This ADR cashes that in.

## Decision

Add a board-level **timeline / Gantt view** implemented as a **read-model projection** over data that already exists. No new write path, no parallel event store.

### 1. The view is a projection, not a new system of record

- **Past lane** — the signed audit stream (ADR 0023). Every transition, nomination, approval, and observation is already timestamped and immutable; the timeline renders them as markers and column-occupancy bands per target.
- **Present / future lane** — anticipated facts: open `WindowOpened`/`WindowClosed` intervals (ISR collection windows, planned actions, shift changes), pending `Nomination` expiries, and `DwellElapsed`/SLA deadlines. These are the forward-looking half the kanban cannot show.

The timeline therefore *contains no truth of its own* — it reads the audit log (past) and the scheduled-window set (future) and lays them on a time axis.

### 2. Lanes are configurable; the data is the same

Lane grouping is a view setting, not a data shape: group rows by **target**, by **board column**, by **assignee/callsign**, or by **window-kind**. The default is per-target rows showing column-occupancy bands + event markers, with a separate lane for scheduled windows. Different domains will prefer different defaults (a SAR planner wants assignee lanes; an ISR scheduler wants window-kind lanes) — that is a per-board/per-template preference, consistent with the malleability principle (ADR 0008).

### 3. Read-first interaction; rescheduling is a deferred write

MVP is read + navigate: zoomable granularity (minutes for tactical, hours/days for planning), and clicking any event deep-links to its card and its audit entry. **Drag-to-reschedule a window is explicitly deferred** — and when it lands, it is *not* a special case: it emits a signal (a window edit) through the ADR 0021 pipeline like any other state change, so it inherits audit and policy for free.

### 4. One read endpoint, all clients

A workspace/board-scoped `/v1` timeline read endpoint (with a time-window parameter) serves the projection. Per ADR 0013 (API client-agnostic), the SPA, mobile, and an ATAK plugin consume the same data — the timeline is not an SPA-only construct.

### 5. Scheduled windows get a lightweight store

The future lane needs somewhere for anticipated intervals to live. A lightweight `ScheduledWindow` record (kind, `valid_from`, `valid_to`, optional target/board scope) owned by the scheduler is the source the future lane projects, and the scheduler emits the `WindowOpened`/`WindowClosed` boundary signals as the injected clock (ADR 0010) reaches them. This is the one piece of genuinely new state — and it is small.

### Concrete rules

- **Read-model only.** The timeline introduces no system of record beyond the `ScheduledWindow` store; past comes from audit, future from windows + nominations.
- **Past = signed audit stream; future = open windows + pending nominations + SLA deadlines.**
- **Lanes are a view preference**, defaulting per board template.
- **Zoomable granularity; events deep-link to card + audit.**
- **Reschedule-by-drag is deferred and, when added, flows through the pipeline as a signal** — never a side-door write.
- **`ScheduledWindow` authoring is access-controlled, and windows cannot bypass policy.** Because `WindowOpened`/`WindowClosed` are *signals*, a window that drives autonomy flows through the same ADR 0021 policy lattice as any other signal — it can only ever `PROPOSE` unless a board policy explicitly trusts that window's source to `ALLOW`. Window create/edit is RBAC'd, and the threat model treats a window as **untrusted autonomy input** until a policy says otherwise — a wrong or hostile window is an authoring-permission boundary, not a free autonomy trigger.

## Alternatives considered

- **A — A standalone scheduling subsystem with its own event store.** Rejected: duplicates the audit + window data, creates a second source of truth, and breaks the "projection, not record" property that keeps this cheap and consistent.
- **B — Time badges on kanban cards only (dwell indicator, aging flag).** Rejected: that is `tw-h4qf`/`tw-k1rb`, useful but not a planning surface — it shows neither the past trajectory nor the planned future, and cannot lay out colliding windows.
- **C — Read-model projection over audit + scheduled windows (this ADR).** Chosen.

## Consequences

**Wins:**
- Completes the SA picture (space + state + **time**) for exactly the planning roles the product targets.
- **Zero workflow-contract change** — the ADR 0021 temporal hook pays off precisely as intended; the view is additive.
- Subsumes and anchors several scattered time features as facets of one surface: dwell (`tw-h4qf`), card aging (`tw-k1rb`), time-of-day brief (`tw-vxdc`), operator handoff (`tw-jn2y`).
- Same data for SPA / mobile / ATAK via one endpoint.

**Trade-offs accepted:**
- Requires the `ScheduledWindow` store + the scheduler that emits boundary signals (shared with ADR 0021's `DwellElapsed`/SLA timers). Small, but it is new state.
- Projecting over a large audit stream needs windowing/pagination to stay fast. **Mitigation:** the read endpoint is time-bounded by default; deep history is paged.
- Lane defaults that suit every domain don't exist — hence they are a per-template preference, decided with each bundled board, not hardcoded here.

## Open questions (refine during implementation, non-blocking)

- Default lane grouping per bundled template (SAR vs ISR vs LE differ).
- Whether `ScheduledWindow` is purely scheduler-owned or also operator-authorable in MVP (leaning: operator-authorable windows are high-value for planners, but can follow the read-only view).

## References

- [ADR 0021 — Workflow decision pipeline](0021-workflow-decision-pipeline.md) — the `valid_from`/`valid_to` + `WindowOpened`/`Closed` temporal hook this view consumes; reschedule-as-signal
- [ADR 0023 — Tamper-evident audit chain](0023-tamper-evident-audit-chain.md) — the past lane *is* the signed audit stream
- [ADR 0013 — API client-agnostic](0013-api-client-agnostic.md) — one timeline endpoint, all clients
- [ADR 0010 — Demo capability / injected clock](0010-demo-capability-post-mvp.md) — the scheduler's controllable clock
- Subsumes/anchors: `tw-h4qf` (dwell), `tw-k1rb` (aging), `tw-vxdc` (time brief), `tw-jn2y` (handoff)
- Implementation: `tw-k4kg.11` (gated by this ADR + the pipeline `tw-k4kg.7`)
