# ADR 0010 — Demo capability is the first post-MVP feature

**Status:** Accepted
**Date:** 2026-05-16

## Context

This project does not have a committed pilot operator. The four flagship mockups are static. Without a demo capability, the product has no way to elicit feedback, draw collaborators, or pressure-test the malleability principle visually.

Demo IS the product validation tool when there is no pilot.

## Decision

Demo capability is a first-class **post-MVP** workstream — sequenced immediately after the MVP architecture lands, before adding the second real Source/Publisher pair.

**Five concrete demo-capability shapes** make up the workstream:

1. **Seed scenarios** — bundled YAML/JSON files that hydrate a workspace on `--profile demo`. Each scenario carries: board template + custom fields + Target catalog + source-event timeline + theme.
2. **Replay engine** — recorded event timeline plays forward at configurable speed (1×, 10×, 60×). A "mission" unfolds in five minutes.
3. **Synthetic source adapter** — first-party `target-workspace-source-synthetic` plugin emits CoT-like detections on a schedule. Keeps workflow pressure realistic.
4. **Guided tour overlay** — Linear/Stripe-style stepped walkthrough; reads tour scripts from `demos/tours/*.yaml`; rendered by the frontend.
5. **Session capture / replay** — record user interactions; replay as re-runnable scenario. Useful for async feedback ("watch me struggle with X").

Demo capability is itself a feature *of* the malleability principle ([ADR 0008](0008-malleability-principle.md)) — a Demo Scenario is just bundled data hydrating the same engine real workspaces use.

## Architectural enablers (carry into MVP so demo capability is cheap later)

These cost nothing now; not having them is what makes demo painful:

- **Injectable clock.** Every place that asks "what time is it?" goes through an injected interface. Production injects the system clock; demo injects a controllable clock (speed, freeze, jump). Without this, replay is impossible.
- **Source-provided timestamps mandatory.** Every event/Target carries a timestamp from its source, not from server-receive. Documented as a load-bearing field in the data model.
- **Scenarios are portable artifacts.** YAML/JSON, importable via the same code path workspaces use to bootstrap. The plugin contract for Sources supports a `seed_data/` path any adapter can read.
- **`target_workspace.demos` entry-points group.** Reserved alongside sources, publishers, etc. Community demo scenarios install via `uv pip install target-workspace-demo-le`.
- **Runtime theme switching.** Demos that swap aesthetic mid-walkthrough prove the malleability principle viscerally; theme is per-session, not per-build.

## Consequences

**Wins:**
- Demo IS our pilot proxy until a real pilot lands
- Same engine, different data — no demo-only codebase to drift
- Community can ship demo scenarios as plugins, growing adoption

**Trade-offs accepted:**
- The five architectural enablers above are non-negotiable in MVP even though only one of them (timestamps) is strictly required by the MVP itself
- Slight upfront design tax for the demo seam vs YAGNI

## Sequencing

1. **Desktop MVP** ships the architecture (single source → single publisher → workflow → audit + tests + CI immune system)
2. **First post-MVP increment: demo capability** — seed scenarios + synthetic source + tour script. Maximum ROI because the engine is already there.
3. **Second post-MVP increment: second real source/publisher pair** — by which point we have something demoable *to* a prospective contact rather than just *for* ourselves.

## References

- [ADR 0008 — Malleability principle](0008-malleability-principle.md)
- [docs/foundation.md §14 — Demo capability architectural enablers](../foundation.md)
