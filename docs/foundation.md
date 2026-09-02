# Foundation

How we set up the project before any feature code is written. Companion to [`tech-stack.md`](tech-stack.md), which pins exact versions.

This document is normative. Any deviation requires an ADR in `docs/adr/`.

## 0. Operating principles

- **TDD red-green-refactor with pre-commit gating.** Failing test before any production code. Pre-commit blocks the commit if the fast-test subset is red.
- **CI/CD is the immune system.** Every gate that can run in CI does run in CI. Red main = no merges until fixed.
- **Supply-chain rigor on day one.** SHA-pinned actions, SBOM, signed images, vuln + license scans in the merge gate.
- **No CVEs at known-high/critical on day one.** Per `tech-stack.md` audit, the pinned versions are clean. Re-audit cadence is explicit there.
- **Malleability is non-negotiable** ([ADR 0008](adr/0008-malleability-principle.md)). The core is rigorously general; the defaults are opinionated; the community owns templates and themes. No hardcoded military terminology in the core.
- **Responsive across every device class** ([ADR 0011](adr/0011-responsive-design.md)). Every production UI works on phone, foldable, tablet, and desktop in both landscape and portrait. No fixed-pixel grid templates. Touch-first interactions.
- **Mobile is a sibling MVP, not a responsive variant** ([ADR 0012](adr/0012-mobile-mvp-separate-scope.md)). Same backend; different focused frontend with its own personas, stories, journeys, and scope.
- **API is a public client-agnostic platform** ([ADR 0013](adr/0013-api-client-agnostic.md)). Web SPA, native mobile, ATAK plugin, third-party integrators, and curl one-liners are equal-class consumers.
- **Demo capability is the first post-MVP feature** ([ADR 0010](adr/0010-demo-capability-post-mvp.md)). Without a committed pilot, the demo is the product validation tool. Architectural enablers for demo capability ride along in MVP.
- **The foundation ships in two commits before any feature work.** Commit A scaffolds the project; Commit B installs the immune system. Then and only then does the first failing test get written.

## 1. Project layout (src + tests + docs + ops)

```
target-workspace/
├── pyproject.toml          # PEP 621 + tool config (ruff, mypy, pytest, coverage, bandit, commitizen)
├── uv.lock                 # committed; reproducible builds
├── .python-version         # "3.13.13"
├── justfile                # dev wrappers: just dev / test / check / build / lint
├── README.md               # already present
├── src/
│   └── target_workspace/
│       ├── __init__.py
│       ├── __about__.py    # __version__
│       ├── contracts/      # plugin Protocols (Source, Publisher, PromotionPolicy, etc.)
│       ├── core/           # workspace engine, audit, RBAC seam
│       ├── plugins/        # first-party adapters (manual source, TAK publisher, raw CoT)
│       ├── api/            # FastAPI routers, dependencies, schemas
│       └── ui/             # served frontend assets (or dev-server proxy in dev)
├── frontend/
│   ├── package.json
│   ├── package-lock.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── components.json     # shadcn config
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── components/
│       │   ├── ui/         # shadcn copy-paste components
│       │   ├── board/      # kanban
│       │   ├── map/        # Cesium / Resium pane
│       │   └── ...
│       └── lib/
├── tests/
│   ├── conftest.py
│   ├── unit/
│   ├── integration/        # testcontainers Postgres
│   └── contract/           # plugin-contract conformance harness
├── docker/
│   ├── Dockerfile          # multi-stage; Chainguard base
│   ├── docker-compose.yml
│   └── docker-compose.prod.yml
├── docs/
│   ├── tech-stack.md       # pinned versions, audit, CVE status
│   ├── foundation.md       # this file
│   ├── design/             # v0.1 design + future revisions
│   ├── research/           # prior-art bundle
│   ├── mockups/            # four flagship HTML mockups
│   ├── personas/           # roster + (future) full profiles
│   └── adr/                # architecture decision records
├── scripts/
│   ├── check.sh            # runs every CI gate locally
│   ├── dev.sh
│   └── verify_sqlite.py    # fails build if bundled SQLite < 3.50.2
├── .github/
│   ├── workflows/
│   │   ├── pr.yml
│   │   ├── main.yml
│   │   ├── release.yml
│   │   ├── nightly.yml
│   │   └── codeql.yml
│   ├── dependabot.yml
│   ├── CODEOWNERS
│   ├── PULL_REQUEST_TEMPLATE.md
│   ├── SECURITY.md
│   └── ISSUE_TEMPLATE/
│       ├── bug.md
│       └── feature.md
├── .pre-commit-config.yaml
├── .gitignore              # already present
└── NOTICES.md              # SpatiaLite LGPL selection, etc.
```

`src` layout (not flat) so imports resolve only from installed package — catches "works on dev box, breaks in container" bugs.

## 2. Test discipline (TDD red-green-refactor enforced)

**Tools** (versions pinned in `tech-stack.md` §D):
- `pytest` + `pytest-asyncio` + `pytest-xdist` + `pytest-cov` + `pytest-watcher`
- `hypothesis` (property-based)
- `httpx` ASGITransport for FastAPI client tests
- `polyfactory` (Pydantic-aware fixtures)
- `testcontainers` (real Postgres + PostGIS in integration tier)
- `mutmut` (mutation testing — verifies tests are meaningful)
- `diff-cover` (coverage on changed lines only)

**Test tiers** (separate dirs, separate markers):
- `tests/unit/` — pure-Python, no I/O, fast. Default marker, always runs.
- `tests/integration/` — real Postgres via testcontainers, real CoT loopback. Marker `@pytest.mark.integration`.
- `tests/contract/` — plugin-contract conformance harness. Marker `@pytest.mark.contract`. Run on every PR.

**Gates:**
| Gate | Threshold | Where |
|---|---|---|
| All tests green | 100% | Pre-commit (unit subset only) + PR + main |
| Branch coverage on changed lines | ≥ 95% | PR (`diff-cover --fail-under=95`) |
| Branch coverage overall | ≥ 90% | PR (`pytest --cov-fail-under=90`) |
| Mutation kill rate | ≥ 80% (changed files) | Nightly workflow |

**TDD loop:**
1. Write the failing test.
2. Run `just watch` (pytest-watcher) — see red.
3. Write the smallest code to make it pass — see green.
4. Refactor with tests green.
5. Pre-commit gates the commit on the unit subset passing.

**TDD-violation tripwires** (rejected at PR):
- New `src/` lines with no corresponding `tests/` lines in the same PR (caught via `diff-cover`).
- `@pytest.mark.skip` without a linked ADR explaining why.
- `# noqa` comments without a code reference.

## 3. Lint / format / type / security

**Tools** (pinned in `tech-stack.md` §D):
- `ruff` — single tool for lint + format + import sort (replaces flake8/black/isort)
- `mypy --strict` — strict mode non-negotiable
- `bandit` — security linter
- `detect-secrets` — block committed secrets
- `pip-audit` — Python dep vuln scan
- `pip-licenses` — license allow-list enforcement (substitute for the rejected `licensecheck`)

**`ruff` config in `pyproject.toml`:**
- Line length 100
- Select: `E`, `F`, `W`, `I`, `B`, `UP`, `C4`, `SIM`, `PT`, `RUF`, `S` (bandit-style security), `ASYNC`, `TRY`, `LOG`
- Per-file ignores documented inline

**`mypy` config:**
- `strict = true`
- `disallow_untyped_defs = true`
- `disallow_any_explicit = false` (allow `Any` only with comment)
- Plugins: pydantic, sqlalchemy

**License enforcement:**
- Allow-list: Apache-2.0, MIT, BSD-2/3, ISC, MPL-2.0, PSF-2.0, PostgreSQL, LGPL (dyn-link), Unlicense, CC0-1.0
- Reject: GPL-family for app code, AGPL, SSPL, "UNKNOWN"
- `pip-licenses --format=json --with-license-file --fail-on="GPL-2.0;GPL-3.0;AGPL-3.0;SSPL"` gates PRs

## 4. Pre-commit (local immune system)

`.pre-commit-config.yaml` — runs on `git commit`:

| Hook | Tool | Purpose |
|---|---|---|
| `ruff check` | ruff | Lint |
| `ruff format` | ruff | Format (auto-fix) |
| `mypy` | mypy | Type-check on changed files |
| `bandit -ll` | bandit | Security linter (low+ severity) |
| `detect-secrets-hook` | detect-secrets | Block committed secrets |
| `check-yaml` / `check-toml` / `check-json` | pre-commit-hooks | Syntax |
| `end-of-file-fixer` / `trailing-whitespace` | pre-commit-hooks | Hygiene |
| `conventional-pre-commit` | conventional-commit | Enforce conventional-commits message format |
| `pytest -m "fast"` | pytest | Fast unit subset only — keeps commit speed sane |

Pre-commit autoupdate runs weekly via a scheduled workflow.

## 5. CI/CD — the production immune system

All GitHub Actions are **SHA-pinned** per `tech-stack.md` §I. Every job runs under `step-security/harden-runner` to sandbox the runner.

### `pr.yml` — every PR must pass

Triggered on `pull_request`. Required status check for merge.

```
1. Checkout (SHA-pinned)
2. harden-runner
3. astral-sh/setup-uv
4. uv sync --frozen
5. ruff check + format --check
6. mypy --strict src tests
7. bandit -r src
8. detect-secrets scan --baseline .secrets.baseline
9. pytest --cov --cov-branch --cov-fail-under=90 (parallel via xdist)
10. diff-cover --fail-under=95 coverage.xml
11. pip-audit --strict
12. pip-licenses --fail-on="GPL-2.0;GPL-3.0;AGPL-3.0;SSPL;UNKNOWN"
13. Frontend: npm ci → eslint → tsc → vitest → vite build
14. Generate SBOM (Syft → CycloneDX) → upload artifact
15. Docker build (no push) → Trivy scan + Grype scan → upload reports
16. All gates green = merge eligible
```

### `main.yml` — push to main

Triggered on push to `main`. Inherits all pr.yml gates, then:

```
17. Build multi-arch image (amd64 + arm64)
18. Push to GHCR tagged :main and :sha-<short>
19. cosign sign --keyless image
20. actions/attest-build-provenance (SLSA v1.0 — replaces stale slsa-github-generator)
21. actions/attest-sbom (attach SBOM as OCI artifact)
22. Verify attestations
```

### `release.yml` — git tag trigger

Triggered on `v*` tags. Inherits main.yml, then:

```
23. release-please runs (Node 24 — note v5.0.0 breaking change)
24. Build versioned image (:v1.2.3, :latest)
25. Generate GitHub release with changelog
26. Attach signed SBOM and attestations to release
```

### `nightly.yml` — scheduled 02:00 UTC

```
- Mutation testing (mutmut run on changed files since last green main)
- OSSF Scorecard refresh
- pip-licenses re-audit (catch upstream license changes)
- uv lock --upgrade in a draft PR (curated upgrades, not auto-merge)
```

### `codeql.yml` — security analysis

```
- Python + TypeScript semantic analysis on push to main + weekly
- Results uploaded to Security tab
```

### `dependabot.yml`

```
- Python deps (uv ecosystem) — weekly, grouped PRs
- npm — weekly, grouped PRs
- GitHub Actions — weekly, security-only auto-merge candidates
- Docker base images — weekly
```

## 6. Docker

**Dockerfile** (multi-stage, distroless-grade final image):

```
# Stage 1: build wheels
FROM cgr.dev/chainguard/python@sha256:<VERIFY-MANUALLY-DIGEST> AS builder
WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --compile-bytecode
COPY src/ ./src/
RUN uv build --wheel

# Stage 2: runtime
FROM cgr.dev/chainguard/python@sha256:<VERIFY-MANUALLY-DIGEST>
USER nonroot
WORKDIR /app
COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /build/dist/*.whl /tmp/
RUN /app/.venv/bin/pip install --no-deps /tmp/*.whl && rm /tmp/*.whl
COPY scripts/verify_sqlite.py /app/
RUN python /app/verify_sqlite.py  # fails build if sqlite < 3.50.2

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz').read()"
ENTRYPOINT ["uvicorn", "target_workspace.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Build commands:**
- `docker buildx build --provenance=true --sbom=true --platform linux/amd64 -t target-workspace:dev -f docker/Dockerfile .`
- Sign: `cosign sign --yes ghcr.io/joshuafuller-labs/target-workspace@<digest>`

**Image scans (CI):**
- `trivy image --severity HIGH,CRITICAL --exit-code 1`
- `grype <image> --fail-on high`

**OCI labels** baked in:
- `org.opencontainers.image.source`
- `org.opencontainers.image.revision`
- `org.opencontainers.image.version`
- `org.opencontainers.image.licenses=MIT`

## 7. Compose / local dev

- `docker/docker-compose.yml` — hobby/dev: app only, SQLite via local volume
- `docker/docker-compose.prod.yml` — prod overlay: adds `postgis/postgis:17-3.6`, optional Cesium tile server
- `justfile` — `just dev`, `just test`, `just check`, `just build`, `just lint`, `just typecheck`, `just lock-upgrade`

## 8. Repository hygiene

**Branch protection on `main`** (configured in GitHub repo settings — not in code, but documented here):
- Require PR; no direct push
- Required status checks: `pr.yml` green
- Required signed commits (commit signing via gitsign or GPG)
- Required reviewer (you as solo; future contributors add to CODEOWNERS)
- No force-push, no deletion

**`.github/` templates:**
- `PULL_REQUEST_TEMPLATE.md` — checklist (test added, ADR if architectural, license-clean, no secrets)
- `ISSUE_TEMPLATE/bug.md` / `feature.md`
- `SECURITY.md` — vuln reporting policy (private security advisory channel via GitHub)
- `CODEOWNERS` — you for now

**Commit hygiene:**
- Conventional Commits enforced via commitizen + pre-commit
- Changelog auto-generated by release-please on tags
- Semver versioning

## 9. Architecture Decision Records (ADRs)

Michael Nygard format. Lightweight markdown in `docs/adr/`.

Initial ADRs to commit alongside scaffolding:
- `0001-record-architecture-decisions.md` — meta
- `0002-python-fastapi-stack.md` — backend choice
- `0003-react-vite-resium-stack.md` — frontend choice
- `0004-cesium-map-pane-in-mvp.md` — Cesium decision
- `0005-plugin-system-entry-points.md` — Python `entry_points` for plugin discovery
- `0006-tdd-and-supply-chain-bar.md` — rationale for TDD + the immune system
- `0008-malleability-principle.md` — core-general / defaults-opinionated / community-owns-templates
- `0009-no-freetakserver-support.md` — explicit exclusion

Every non-trivial future decision gets an ADR; future-you will thank present-you.

## 10. Observability foundations

- **structlog** — JSON logs with request-id, trace-id, user-id propagated via context
- **OpenTelemetry** — traces + metrics + logs via OTLP exporter; config-driven; in dev no exporter is forced
- **Endpoints:**
  - `GET /healthz` — liveness (always-200 if process is running)
  - `GET /readyz` — readiness (checks DB, plugin discovery, TAK reachability if configured)
  - `GET /metrics` — Prometheus or OTel-native (env-controlled)

## 11. Configuration

- **pydantic-settings** — env-driven, type-safe, validated at boot
- `.env.example` committed; `.env` gitignored
- Twelve-factor compliance
- Secrets in env (Vault / SOPS deferred until needed)

## 12. Documentation

- **mkdocs-material** (Apache-2) for site generation
- API reference auto-generated from FastAPI OpenAPI
- ADRs above
- Documentation can be hosted directly from the public repository.

## 13. Plugin contract scaffolding

`src/target_workspace/contracts/` — Python `Protocol` classes for:
- `Source` — receive detections (manual, webhook, CoT-in, …)
- `Publisher` — emit events (TAK Server, raw CoT, webhook-out, …)
- `PromotionPolicy` — gated / conditional / autonomous
- `ClassificationScheme` — tag schema (U/CUI/S, or LE Sensitive/Public/Sealed, or none)
- `Theme` — UI palette + typography + iconography
- `BoardTemplate` — column set + transition rules + default policy

Each `Protocol` has a corresponding conformance test fixture in `tests/contract/` that any implementation can be run against.

Plugin discovery via `importlib.metadata.entry_points()`:
- Groups: `target_workspace.sources`, `target_workspace.publishers`, `target_workspace.policies`, `target_workspace.classifications`, `target_workspace.themes`, `target_workspace.boards`
- First-party adapters live in `src/target_workspace/plugins/` and register via the same mechanism (entry_points declared in this package's `pyproject.toml`)
- Future external plugins are installable via `uv pip install target-workspace-source-mqtt` and discovered without core changes

## 14. Architectural enablers for demo capability (carried into MVP)

Per [ADR 0010](adr/0010-demo-capability-post-mvp.md), demo capability is the first post-MVP feature. Five architectural enablers ride along in MVP so the post-MVP demo work is cheap:

- **Injectable clock.** Every place that asks "what time is it?" routes through an injected `Clock` interface (Protocol class in `src/target_workspace/contracts/clock.py` when written). Production injects the system clock; demo replay injects a controllable clock (speed, freeze, jump). Without this, the replay engine is impossible.
- **Source-provided timestamps mandatory.** Every event/Target carries a timestamp from its source, not from server-receive. Server-receive is an additional field for audit; never overrides source.
- **Scenarios as portable artifacts.** YAML/JSON, importable via the same code path workspaces use to bootstrap. The Source contract supports a `seed_data/` path any adapter can read.
- **`target_workspace.demos` entry-points group reserved.** Alongside sources, publishers, etc. Community demo scenarios install via `uv pip install target-workspace-demo-le`.
- **Runtime theme switching.** Themes are per-session, not per-build. Demos swap aesthetic mid-walkthrough to prove malleability.

## 15. Architectural enablers for mobile MVP (carried into MVP)

Per [ADR 0012](adr/0012-mobile-mvp-separate-scope.md), mobile is its own MVP. Architectural decisions in the desktop MVP must NOT preclude it:

- **API is client-agnostic** ([ADR 0013](adr/0013-api-client-agnostic.md)). Multiple auth modes coexist; OpenAPI is the public contract; pagination/filtering/sorting standardized; WebSocket and SSE both supported; uploads via multipart AND pre-signed URLs; RFC 7807 errors; `Idempotency-Key` accepted on all POSTs.
- **Offline-first sync semantics placeholder in data model.** Server-issued IDs, monotonic version/etag per object, conflict-resolution hooks. Desktop MVP doesn't need them at runtime, but the schema reserves the fields.
- **Capture-focused endpoints sketched.** `POST /v1/capture` with photo + GPS + minimal Target schema. Mobile MVP doesn't have to invent its own ingestion path.
- **Mobile-only features as plugins.** Camera capture, GPS auto-fill, push notifications — implemented as their own modules, not woven into the desktop frontend.

## 16. Responsive design baseline (every production UI)

Per [ADR 0011](adr/0011-responsive-design.md), every production UI surface is responsive across phone / foldable / tablet / desktop in both orientations:

- **No fixed-pixel grid templates in production code.** Use `repeat(auto-fit, minmax(<min>, 1fr))` or container queries. The four flagship HTML mockups are example desktop themes and are exempt — production code is held to this bar.
- **Tested at multiple viewports in CI.** Playwright suite runs at 360×800, 412×915, 720×1024, 1024×720, 1440×900, 1920×1080. Detection asserts: no horizontal overflow, no track widths < 80px, no overlapping siblings inside `<main>`.
- **Touch-first.** Hit targets ≥ 44px; long-press for right-click-equivalent context menus; no hover-only affordances.
- **Cesium 2D default on mobile.** 3D toggle exists; default per-viewport is responsive based on device capability.

## 17. Explicitly deferred (NOT in foundation; do not bolt on early)

| Item | Why deferred |
|---|---|
| Vault / SOPS for secrets | Wait until first non-env-friendly secret appears |
| Helm chart | Wait until k8s deploy is real |
| Plugin marketplace / registry | Out of MVP entirely |
| Jaeger / Tempo deployment | Config seam exists; deployment doesn't |
| `LICENSE` file | License posture tabled (`feedback_target_workspace_license_tabled.md`) |
| Public docs hosting | Tied to license decision |
| Multi-tenancy | Out of MVP |
| OIDC / multi-user RBAC | Auth seam ships; full OIDC integration is post-MVP |
| Themes as switchable products | Bundled templates only in MVP |
| Map pane | **In MVP** (Cesium) — listed here only to refute speculation |
| FreeTAKServer support | Explicitly excluded, do not propose |

## 18. Bootstrap sequence

Two commits before any feature code.

### Commit A — "Project scaffolding"

Files added:

```
pyproject.toml
uv.lock
.python-version
justfile
src/target_workspace/__init__.py
src/target_workspace/__about__.py
src/target_workspace/contracts/__init__.py   # empty Protocol stubs
tests/__init__.py
tests/conftest.py
tests/unit/test_smoke.py                      # one deliberately failing + one passing test
tests/contract/__init__.py
tests/integration/__init__.py
frontend/package.json
frontend/package-lock.json
frontend/tsconfig.json
frontend/vite.config.ts
frontend/tailwind.config.ts
frontend/index.html
frontend/src/main.tsx                         # mounts a single placeholder component
docker/Dockerfile
docker/docker-compose.yml
docker/docker-compose.prod.yml
scripts/check.sh
scripts/dev.sh
scripts/verify_sqlite.py
mkdocs.yml
NOTICES.md
docs/adr/0001-record-architecture-decisions.md
docs/adr/0002-python-fastapi-stack.md
docs/adr/0003-react-vite-resium-stack.md
docs/adr/0004-cesium-map-pane-in-mvp.md
docs/adr/0005-plugin-system-entry-points.md
docs/adr/0006-tdd-and-supply-chain-bar.md
docs/adr/0007-license-tabled.md
docs/adr/0008-malleability-principle.md
docs/adr/0009-no-freetakserver-support.md
.gitignore                                    # update
```

Acceptance criteria for Commit A:
- `uv sync --frozen` succeeds
- `pytest` runs and reports 1 pass + 1 fail (the deliberate failing test, proving infra)
- `docker buildx build` succeeds locally (image not pushed)
- `just check` runs and stops at the deliberate failing test
- `mkdocs serve` renders

### Commit B — "CI/CD immune system"

Files added:

```
.github/workflows/pr.yml
.github/workflows/main.yml
.github/workflows/release.yml
.github/workflows/nightly.yml
.github/workflows/codeql.yml
.github/dependabot.yml
.github/CODEOWNERS
.github/PULL_REQUEST_TEMPLATE.md
.github/SECURITY.md
.github/ISSUE_TEMPLATE/bug.md
.github/ISSUE_TEMPLATE/feature.md
.pre-commit-config.yaml
.secrets.baseline                             # detect-secrets baseline
pyproject.toml                                # updated with ruff/mypy/pytest/coverage/bandit/commitizen config
tests/unit/test_smoke.py                      # the deliberate failing test is now made green (TDD demo)
```

Acceptance criteria for Commit B:
- `pre-commit run --all-files` passes
- `act` (or pushed CI) runs `pr.yml` green
- All workflow files reference SHA-pinned action versions per `tech-stack.md` §I
- The previously-failing smoke test is now green (TDD red→green demonstration)

After A + B land green on main, **feature work begins**. First feature commit must be preceded by a failing test.

## 19. Pre-flight checklist — must be ✓ before Commit A is pushed

- [ ] `tech-stack.md` reviewed and approved by Joshua
- [ ] Chainguard image digest resolved via `crane digest` and locked in `Dockerfile`
- [ ] All GitHub Action SHAs in `tech-stack.md` §I resolved to full 40-char form via `gh api`
- [ ] Trivy supply-chain advisory cross-checked against StepSecurity's clean-pin guidance
- [ ] `tests/unit/test_smoke.py` written with one deliberately failing test (red) and one passing test
- [ ] `NOTICES.md` documents SpatiaLite LGPL-2.1+ selection and PostGIS networked-use exception
- [ ] `.secrets.baseline` generated via `detect-secrets scan > .secrets.baseline`
- [ ] Branch protection rules drafted (will apply post-Commit B once `pr.yml` exists to require)

After Commit B lands green:
- [ ] Branch protection enabled on `main`
- [ ] Signed-commits requirement enabled
- [ ] Required status checks: `pr.yml` set as required
- [ ] No-force-push, no-deletion enforced

## 20. What this foundation enables

- Day-1 secure: zero high/critical CVEs in pinned versions, SBOM + signed images on every release, license allow-list enforced at PR gate.
- Day-1 testable: TDD enforced by pre-commit + CI; mutation testing nightly; coverage gated.
- Day-1 reproducible: locked dependencies, pinned Docker base by digest, pinned actions by SHA.
- Day-1 malleable: plugin contracts exist before adapters are written; entry_points discovery is the production-grade Python pattern, not invented.
- Day-1 hobbyist-runnable AND prod-runnable: single `docker run` for SQLite hobby tier; same image with env config for Postgres+PostGIS prod tier.
- Future-friendly: ADRs preserve reasoning; explicit deferral list keeps scope honest.
