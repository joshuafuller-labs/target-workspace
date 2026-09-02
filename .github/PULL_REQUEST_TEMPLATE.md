<!-- Thank you for the PR. Fill in the sections below; the merge gate enforces most of it. -->

## What changed

<!-- One paragraph: what does this PR do, and why? -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor / cleanup
- [ ] Test infrastructure
- [ ] CI / supply-chain
- [ ] Docs / ADR
- [ ] Dependency update

## Checklist

- [ ] New code is preceded by a failing test (TDD red→green→refactor)
- [ ] Tests added cover the new code paths; diff coverage ≥ 95%
- [ ] `just check` is green locally (or CI is green)
- [ ] No new dependencies outside the license allow-list (Apache-2 / MIT / BSD / ISC / MPL-2 / PSF / LGPL-dyn)
- [ ] No secrets committed (detect-secrets baseline updated if intentional false positive)
- [ ] If architectural: an ADR has been added or amended in `docs/adr/`
- [ ] If touching the API: OpenAPI spec was regenerated and is committed
- [ ] If touching the frontend: tested at least two viewports (phone portrait, desktop) and one orientation flip
- [ ] If touching plugin contracts: conformance tests still pass for all in-tree adapters

## Related ADRs / issues

<!-- Closes #N, Refs ADR 0013, etc. -->
