# ADR 0009 — No FreeTAKServer (FTS) support

**Status:** Accepted
**Date:** 2026-05-16

## Context

Early design considered FreeTAKServer (FTS) as a secondary publisher target alongside TAK Server (official) and raw CoT emit. The owner subsequently directed that FTS support be removed entirely from the project.

## Decision

Target Workspace does **not** support FreeTAKServer as a Source or Publisher target. The publisher matrix is:
- **TAK Server (official)** — primary production target
- **Raw CoT emit** (TCP/UDP/SSL) — lowest-common-denominator fallback
- **Webhook out** — generic HTTP POST

FTS, OpenTAKServer (OTS), and other community TAK Server reimplementations are out of scope. They may be referenced in research documents as observable landscape (they exist), but no first-party adapter will target them, and no design implication will assume their presence.

## Consequences

**Wins:**
- Smaller test matrix
- No commitment to FTS API compatibility (FTS evolves separately and could break us)
- Clear single primary integration target

**Trade-offs accepted:**
- Hobby users running FTS lose a first-party path. They can either use the raw CoT publisher (works against any CoT listener) or write a community Publisher adapter against the plugin contract.

**Anti-patterns this ADR explicitly forbids:**
- Adding `fts` as a publisher type enum value
- Referencing FreeTAKServer in default configs, board templates, or any first-party plugin
- Citing FTS-specific behaviors as design constraints

## References

- Agent memory: `project_target_workspace.md` (anti-patterns list)
- Owner direction recorded in session on 2026-05-16
