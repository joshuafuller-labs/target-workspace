# ADR 0008 — Malleability is the product's load-bearing principle

**Status:** Accepted
**Date:** 2026-05-16

## Context

Target Workspace serves four different customer worlds (DoD tactical, DoD operational, federal LE, state/local SAR) plus hobbyist / community / OSINT-investigator users. The owner's explicit framing: "no one will want the same thing and focusing too hard on one specific use case, i.e. the military, means open-source random users will never adopt this. It must be malleable."

Over-fitting to military terminology, workflow, or compliance assumptions kills hobby/community adoption and locks the product to a narrow buyer set.

## Decision

The architecture follows three layers:

1. **The core is rigorously general.** Vocabulary is neutral. "Target" stays (it's the CoT word). Stage names, affiliation taxonomies, classification systems, source/publisher types, themes — all data, not code.
2. **The defaults are opinionated.** Bundled templates (F3EAD, D3A, LE case, SAR), bundled themes (the four flagship aesthetics), bundled classification schemes (DoD US, LE standard, none) ship with sensible factory settings.
3. **The community owns templates and themes.** Plugin contracts (Source / Publisher / PromotionPolicy / ClassificationScheme / Theme / BoardTemplate) are first-class. Adapters are `uv pip install`-distributable.

This is the Postgres / VS Code / k8s pattern: rigorous platform, opinionated defaults, infinite customization at the edges.

**Concrete rules:**
- No hardcoded military terminology in the core (no "FINISH" column in default schema; no CJCSI 3370.01 taxonomy in core; no MIL-STD-2525 symbology required)
- Compliance (CJIS audit, classification handling, FedRAMP path, ABAC) ships as optional modules, not core
- Defaults must work for a single-container hobbyist (SQLite, no auth, one `docker run`)
- Plugin SDK is a product surface, not an afterthought

## Consequences

**Wins:**
- Same binary runs on a Raspberry Pi (hobbyist) and a DoD k8s cluster (fed) with layered config
- Open-source adoption viable (when license settles) — no aggressive military framing in core
- Community contributions land as plugins, not core forks
- Future customer segments (e.g., disaster response, journalism, citizen science) require no core rewrite

**Trade-offs accepted:**
- More upfront design effort for plugin contracts before any feature ships
- Risk of "platform for everyone, product for no one" if MVP fails to pick a concrete demo use case. **Mitigation:** MVP picks one demo path and runs it end-to-end (manual → TAK → audit); the malleability is proven by *running the same demo through different bundled templates*, not by claiming abstractness
- Refusing to fold customer-specific feedback into core when a single big customer asks

## References

- Agent memory: `feedback_target_workspace_malleability.md`
- [docs/foundation.md §13](../foundation.md) — plugin contract scaffolding
- [src/target_workspace/contracts/](../../src/target_workspace/contracts/) — the six Protocol classes
