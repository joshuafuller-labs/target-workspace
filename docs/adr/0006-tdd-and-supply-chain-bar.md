# ADR 0006 — TDD red-green-refactor + CI/CD as the immune system

**Status:** Accepted
**Date:** 2026-05-16

## Context

Joshua's standing preferences (captured in agent memory) require TDD with pre-commit gating and supply-chain rigor on greenfield projects. The user explicitly framed CI/CD as "the immune system" of the project. The foundation ships before any feature code; the bar is "rock solid foundation, no CVEs out of the gate."

## Decision

**TDD discipline:**
- Failing test before any production code (red)
- Smallest possible code to pass (green)
- Refactor with green bar (refactor)
- Pre-commit hook runs the fast-test subset; commits fail if tests fail
- PR gate: full pytest suite + 90% branch coverage overall + 95% on diff (`diff-cover`)
- Nightly: mutation testing (`mutmut`) — verifies the tests are meaningful, not just present

**Supply-chain rigor:**
- Every GitHub Action SHA-pinned (40-char commit) with tag in trailing comment
- `step-security/harden-runner` on every job
- SBOM (Syft → CycloneDX) generated at every PR; attached as OCI artifact on every release image
- Cosign keyless signing on every release image
- `actions/attest-build-provenance` for SLSA v1.0 provenance (replaces stale `slsa-github-generator`)
- Vuln scanning: `pip-audit` for Python; Trivy + Grype for containers
- License allow-list enforced at PR gate via `pip-licenses --fail-on`
- `detect-secrets` baseline + pre-commit hook
- Dependabot weekly for Python, npm, GitHub Actions, Docker base images

**The first failing CI run is intentional:** `tests/unit/test_smoke.py::test_red_to_be_resolved_in_commit_b` deliberately fails on Commit A. Commit B turns it green, demonstrating the TDD red→green cycle on real CI against the real foundation.

## Consequences

**Wins:**
- Zero CVEs in pinned versions on day 1 (validated by [docs/tech-stack.md](../tech-stack.md))
- Mutation testing prevents "100% coverage but tests don't actually test anything"
- Reproducible builds via locked deps and SHA-pinned actions
- Supply-chain incidents (Trivy v0.69.4-style) caught by version-incident-paused builds
- Future contributors (if any) inherit a hardened workflow, not bolted-on later

**Trade-offs accepted:**
- Pre-commit hook adds 2-5 seconds to every commit (acceptable; reflects the bar)
- Mutation testing in CI is slow (nightly, not per-PR)
- SHA pinning requires periodic refresh when actions release new versions (Dependabot manages this)
- ~1 day of upfront foundation work before any feature code

## References

- Agent memory: `feedback_tdd_preferred.md`, `feedback_supply_chain_rigor.md`
- [docs/foundation.md §2-5](../foundation.md) — TDD discipline, CI/CD specifics
- [docs/tech-stack.md](../tech-stack.md) — audit and version pins
