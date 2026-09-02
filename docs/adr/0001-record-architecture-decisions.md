# ADR 0001 — Record architecture decisions

**Status:** Accepted
**Date:** 2026-05-16

## Context

This project is in pre-MVP, pre-code phase. Decisions are accumulating fast — tech stack, malleability principle, license posture, MVP scope, supply-chain bar, plugin model. Each decision narrows future choices and has reasoning that will not be reconstructible from the code alone.

A solo project with no team is the *most* likely to forget *why* a decision was made — there's nobody to ask in two months.

## Decision

We use lightweight Architecture Decision Records in `docs/adr/`, Michael Nygard format. Numbered sequentially, dated, with explicit status (Proposed / Accepted / Superseded by X / Deprecated). One non-trivial decision per ADR.

Every ADR captures:
- The context that forced the decision
- The decision itself, stated unambiguously
- The consequences (good, bad, and acknowledged trade-offs)

## Consequences

- Future-me has a written record of intent, not just outcome.
- New contributors (if/when) have a single place to learn the system's reasoning.
- Superseded decisions stay visible — we never silently rewrite history; we add a new ADR that supersedes the old.
- ~30 minutes of writing overhead per non-trivial decision; cheap insurance against rework.

## References

- https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions
- https://adr.github.io/
