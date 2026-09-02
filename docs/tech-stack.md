# Tech Stack — pinned manifest

**Audit date:** 2026-05-16
**Audit method:** vendor release pages, OSV.dev, GitHub Security Advisories, PyPI Advisory DB, NVD cross-referenced for every component below.
**Audit result:** zero high/critical CVEs known-present in any pinned version. Several components had high-severity issues in earlier 2026 releases (Authlib, python-multipart, Starlette pre-0.49.1, Vite pre-8.0.5, Cryptography pre-46.0.7, PostgreSQL pre-17.10) — all patched in the pins below.

## Policy

**License allow-list** — Apache-2.0, MIT, BSD (any), ISC, MPL-2.0, PSF, PostgreSQL License, LGPL when dynamically linked only.
**Rejected** — GPL family for application code, AGPL anywhere, SSPL anywhere.
**Networked GPL services are acceptable** (PostgreSQL extension PostGIS over libpq); see Notes for guardrails.

**Pin strategy:**
- **Exact pin (`==X.Y.Z`)** for API-defining libraries: pydantic, FastAPI, sqlmodel, react, cesium, bcrypt, authlib.
- **Range pin (`>=X.Y,<X.(Y+1)`)** for monotonically-improving security/QA tools: ruff, mypy, pytest, bandit, pip-audit.
- **SHA pin (40-char commit)** for all GitHub Actions, tag in trailing comment. See section I.

## Hard rejects — do NOT install

| Library | Reason | Substitute |
|---|---|---|
| `passlib` | Unmaintained since 2020; relies on removed `crypt` module; incompatible with bcrypt 5.x | Use `bcrypt` directly with `bcrypt.hashpw()` / `bcrypt.checkpw()` |
| `licensecheck` (FHPythonUtils) | Last release 2025.1.0; package metadata declares Python 3.8–3.11 only; will not run on 3.13 | `pip-licenses` (MIT) or `liccheck` (Apache-2.0) |
| `pyspatialite` | Deprecated, unmaintained | Stdlib `sqlite3` with `connection.load_extension('mod_spatialite')` |
| `aquasecurity/trivy` v0.69.4 | Malicious release published Feb/Mar 2026; concurrent compromise of `setup-trivy` and `trivy-action` | Pin trivy binary to `v0.70.0` exactly; pin actions to audited SHAs from before the incident or post-incident clean releases |
| `slsa-framework/slsa-github-generator` | Last release Feb 2024 — stale | GitHub-native `actions/attest-build-provenance` + `actions/attest-sbom` (SLSA v1.0-compliant, actively maintained) |

## A. Python runtime & core

| Component | Pinned version | License | Source |
|---|---|---|---|
| CPython | `3.13.13` | PSF | https://www.python.org/downloads/release/python-31313/ |
| FastAPI | `fastapi==0.136.1` | MIT | https://pypi.org/project/fastapi/ |
| uvicorn | `uvicorn[standard]==0.47.0` | BSD-3-Clause | https://pypi.org/project/uvicorn/ |
| starlette | `starlette>=1.0.0,<1.1.0` (explicit floor for CVE-2025-62727 protection) | BSD-3-Clause | https://github.com/Kludex/starlette/releases |
| pydantic | `pydantic==2.13.4` | MIT | https://pypi.org/project/pydantic/ |
| pydantic-settings | `pydantic-settings==2.14.1` | MIT | https://pypi.org/project/pydantic-settings/ |
| SQLModel | `sqlmodel==0.0.38` (pre-1.0 API still moves; exact pin) | MIT | https://pypi.org/project/sqlmodel/ |
| SQLAlchemy | `SQLAlchemy>=2.0.49,<2.1` (avoid 2.1 betas) | MIT | https://pypi.org/project/SQLAlchemy/ |
| alembic | `alembic>=1.18.4,<1.19` | MIT | https://pypi.org/project/alembic/ |
| bcrypt | `bcrypt==5.0.0` (exact pin; 5.x is API break vs 4.x) | Apache-2.0 | https://pypi.org/project/bcrypt/ |
| authlib | `Authlib==1.7.2` (post 4×CVE patch line) | BSD-3-Clause | https://pypi.org/project/Authlib/ |
| structlog | `structlog>=25.5.0,<26` | Apache-2.0 / MIT dual | https://pypi.org/project/structlog/ |
| python-multipart | `python-multipart==0.0.28` (post-CVE-2026-40347) | Apache-2.0 | https://pypi.org/project/python-multipart/ |
| cryptography | `cryptography>=48.0.0,<49` (transitive; explicit floor for CVE-2026-39892) | Apache-2.0 / BSD-3 dual | https://github.com/pyca/cryptography/blob/main/CHANGELOG.rst |

## B. Observability

| Component | Pinned version | License |
|---|---|---|
| opentelemetry-api | `opentelemetry-api>=1.41.1,<1.42` | Apache-2.0 |
| opentelemetry-sdk | `opentelemetry-sdk>=1.41.1,<1.42` | Apache-2.0 |
| opentelemetry-exporter-otlp | `opentelemetry-exporter-otlp>=1.41.1,<1.42` | Apache-2.0 |
| opentelemetry-instrumentation-fastapi | `opentelemetry-instrumentation-fastapi==0.62b1` (contrib beta-version naming is the stable line) | Apache-2.0 |
| opentelemetry-instrumentation-sqlalchemy | `opentelemetry-instrumentation-sqlalchemy==0.62b1` | Apache-2.0 |

## C. CoT (Cursor on Target)

| Component | Pinned version | License | Source |
|---|---|---|---|
| pytak | `pytak==7.2.1` | Apache-2.0 | https://pypi.org/project/pytak/ |
| takproto | `takproto==3.0.1` | MIT | https://pypi.org/project/takproto/ |

## D. Testing & quality

| Component | Pinned version | License |
|---|---|---|
| pytest | `pytest>=9.0.3,<10` | MIT |
| pytest-asyncio | `pytest-asyncio>=1.3.0,<2` (skip 1.4.0a alphas) | Apache-2.0 |
| pytest-cov | `pytest-cov>=7.1.0,<8` | MIT |
| pytest-xdist | `pytest-xdist>=3.8.0,<4` | MIT |
| pytest-watcher | `pytest-watcher>=0.6.3,<1` | MIT |
| hypothesis | `hypothesis>=6.152.7,<7` | MPL-2.0 |
| httpx | `httpx==0.28.1` (no new release in ~17mo; exact pin) | BSD-3-Clause |
| polyfactory | `polyfactory>=3.3.0,<4` | MIT |
| testcontainers | `testcontainers>=4.14.2,<5` | Apache-2.0 |
| mutmut | `mutmut>=3.5.0,<4` (v3 changed execution model from v2; aware) | BSD-3-Clause |
| diff-cover | `diff-cover>=10.2.0,<11` | Apache-2.0 |
| ruff | `ruff>=0.15.12,<0.16` | MIT |
| mypy | `mypy>=2.1.0,<3` | MIT |
| bandit | `bandit[toml]>=1.9.4,<2` | Apache-2.0 |
| detect-secrets | `detect-secrets==1.5.0` (stale-velocity warning; revisit annually) | Apache-2.0 |
| pip-audit | `pip-audit>=2.10.0,<3` | Apache-2.0 |
| pip-licenses | `pip-licenses>=5.0,<6` (substitute for licensecheck) | MIT |
| pre-commit | `pre-commit>=4.6.0,<5` | MIT |
| commitizen | `commitizen>=4.16.0,<5` | MIT |

## E. Frontend (Node / npm)

| Component | Pinned version | License |
|---|---|---|
| react | `19.2.6` | MIT |
| react-dom | `19.2.6` | MIT |
| @types/react | `19.2.14` | MIT |
| @types/react-dom | `19.2.3` | MIT |
| typescript | `6.0.3` (TS 7 is in beta — do NOT adopt) | Apache-2.0 |
| vite | `8.0.13` (post CVE-2026-39363/4/5) | MIT |
| @cesium/engine | `24.0.0` (split-package model preferred over legacy `cesium`) | Apache-2.0 |
| @cesium/widgets | `14.0.0` | Apache-2.0 |
| resium | `1.20.0` | MIT |
| tailwindcss | `4.3.0` | MIT |
| @tanstack/react-query | `5.100.10` | MIT |
| zustand | `5.0.13` | MIT |
| shadcn (CLI, dev only) | `4.7.0` (v4 was a March 2026 breaking-change release; we adopt v4 cleanly) | MIT |

## F. Build & supply-chain tooling

| Component | Pinned version | License |
|---|---|---|
| uv | `uv==0.11.14` | Apache-2.0 / MIT dual |
| syft | image `anchore/syft:v1.44.0` | Apache-2.0 |
| grype | image `anchore/grype:v0.112.0` | Apache-2.0 |
| trivy | image `aquasec/trivy:0.70.0` (exact pin only — see hard rejects) | Apache-2.0 |
| cosign | binary `v3.0.6` | Apache-2.0 |
| harden-runner | `v2.19.3` (SHA-pin in CI) | MIT |

## G. Container base images

| Image | Pin form | Notes |
|---|---|---|
| Chainguard Python (preferred) | `cgr.dev/chainguard/python@sha256:1cb3c5da9785e2f3b13bc46450686ae69e688038c590dc5247b7a98e578ec6db` (resolved 2026-05-16; Python 3.14 series) | `:latest-3.13` is paid-tier only on Chainguard's free public registry — we pin `:latest` by digest and accept the current major (3.14). Refresh digest on Dockerfile bump. |
| Chainguard wolfi-base (alt) | `cgr.dev/chainguard/wolfi-base@sha256:<digest>` | Only if Python image insufficient |
| PostgreSQL (prod) | `postgres:17.10-bookworm` | Post 11-CVE fix release; supported through Nov 2029 |
| PostGIS (prod) | `postgis/postgis:17-3.6` | Pair with Postgres 17.x. PostGIS license is GPL-2.0 — see Notes |

## H. Infrastructure

| Component | Pinned version | License | Notes |
|---|---|---|---|
| PostgreSQL | major `17` (current `17.10`); fallback major `16` | PostgreSQL License | Networked use only |
| PostGIS | `3.6.x` paired with Postgres 17 | GPL-2.0 (networked-service exception, NOT linked into app) | See Notes 11 |
| SQLite | bundled with CPython 3.13.13 (≥ 3.50.2 baseline) | Public Domain | Verify at image build: `python3 -c "import sqlite3; print(sqlite3.sqlite_version)"` and fail build if < 3.50.2 |
| SpatiaLite | `5.1.0` via `mod_spatialite` (dynamic load) | tri-license; we select **LGPL-2.1+** at use time | Document in `NOTICES.md` |

## I. GitHub Actions — SHA-pinned

All actions pinned to the full 40-character commit SHA with the tag in a trailing comment. Where the audit returned a short SHA, the entry is marked **VERIFY MANUALLY** and must be resolved via `gh api repos/<owner>/<repo>/git/ref/tags/<tag>` at the moment the workflow file is committed.

| Action | Tag | Pin guidance |
|---|---|---|
| `actions/checkout` | `v6.0.2` | `de0fac2e4500dabe0009e67214ff5f5447ce83dd` (resolved 2026-05-16) |
| `actions/checkout` (fallback) | `v5.0.0` | `08c6903cd8c0fde910a37f88322edcfb5dd907a8` |
| `astral-sh/setup-uv` | `v8.1.0` | `08807647e7069bb48b6ef5acd8ec9567f424441b` |
| `actions/setup-python` | `v6.2.0` | `a309ff8b426b58ec0e2a45f0f869d46889d02405` |
| `step-security/harden-runner` | `v2.19.3` | `ab7a9404c0f3da075243ca237b5fac12c98deaa5` |
| `sigstore/cosign-installer` | `v4.1.2` | `6f9f17788090df1f26f669e9d70d6ae9567deba6` (resolved 2026-05-16; STALE FLAG retained — installer last updated 2024-05 but installs current cosign 3.0.6 binary) |
| `anchore/sbom-action` | `v0.24.0` | `e22c389904149dbc22b58101806040fa8d37a610` |
| `anchore/scan-action` | `v7.4.0` | `e1165082ffb1fe366ebaf02d8526e7c4989ea9d2` |
| `aquasecurity/trivy-action` | `v0.36.0` | `ed142fd0673e97e23eac54620cfb913e5ce36c25` (resolved 2026-05-16; post-incident clean release — confirm against StepSecurity advisory before each upgrade) |
| `github/codeql-action` | `v4.35.5` | `9e0d7b8d25671d64c341c19c0152d693099fb5ba` |
| `actions/attest-build-provenance` | latest GA | Use instead of `slsa-framework/slsa-github-generator` |
| `actions/attest-sbom` | latest GA | Pair with `attest-build-provenance` |
| `googleapis/release-please-action` | `v5.0.0` | `45996ed1f6d02564a971a2fa1b5860e934307cf7` — note: requires Node 24 |
| `actions/upload-artifact` | `v7.0.1` | `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` — v5+ forbids duplicate artifact names |
| `actions/download-artifact` | `v8.0.1` | `3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c` |

## Notes & call-outs

1. **passlib** — Do not include. See hard rejects.
2. **licensecheck (FHPythonUtils)** — Do not include. See hard rejects. Substitute `pip-licenses`.
3. **Trivy supply-chain incident (Feb–Mar 2026)** — The single largest live supply-chain warning on this stack. `v0.69.4` was malicious; `setup-trivy` and `trivy-action` were concurrently compromised. Pin only to `v0.70.0`, audit all SHAs against StepSecurity's published clean-pin advisory before committing CI YAML. Ref: https://www.stepsecurity.io/blog/trivy-compromised-a-second-time---malicious-v0-69-4-release
4. **Starlette transitive pin** — FastAPI 0.136.1 brings starlette in a compatible range; the explicit `starlette>=1.0.0,<1.1.0` line in `pyproject.toml` hardens against accidental downgrade across the CVE-2025-62727 fix line.
5. **OpenTelemetry contrib beta naming** — `opentelemetry-instrumentation-*` packages use intentional `0.NNbX` versioning even though they are the official release stream coupled to stable `1.41.x` core. Not actually pre-release.
6. **CesiumJS split-package model** — Use `@cesium/engine` + `@cesium/widgets`. The legacy single `cesium` package is in maintenance mode.
7. **TypeScript 7 beta** — Go-based compiler in beta as of April 2026. Do NOT adopt for security-sensitive code; pin TS 6.0.3.
8. **SQLAlchemy 2.1 beta** — 2.1.0b2 exists. Stay on 2.0.x stable.
9. **detect-secrets velocity** — Last release May 2024. Still functional, no CVEs. Revisit in 6 months; consider `gitleaks` or `trufflehog` if dormant.
10. **httpx velocity** — 0.28.1 from Dec 2024, no new releases in ~17 months. No CVEs. Still standard.
11. **PostGIS license carve-out** — PostGIS is GPL-2.0. It runs as a database-server extension over libpq, not linked into application code. This satisfies the policy carve-out for GPL components used as separate network services. **DO NOT** statically link or distribute the PostGIS shared library inside the application container.
12. **SpatiaLite license selection** — Tri-licensed MPL-1.1 / LGPL-2.1+ / GPL. We select **LGPL-2.1+** at use time, used via dynamic load (`mod_spatialite`). Document in `NOTICES.md`.
13. **Chainguard image pinning** — Tags are rolling. Pin by digest (`@sha256:...`) at first image build. Marked **VERIFY MANUALLY**.
14. **GitHub Actions SHA verification** — Resolve any short SHAs to full 40-character form via `gh api repos/<owner>/<repo>/git/ref/tags/<tag>` before committing workflow YAML.
15. **slsa-github-generator staleness** — Last release Feb 2024. Use GitHub-native `actions/attest-build-provenance` (SLSA v1.0-compliant, actively maintained).
16. **Authlib history** — Four high-severity CVEs (28498, 28802, 28490, 27962) patched in 1.6.9+. Pinned 1.7.2 is safe. Do not allow Dependabot to downgrade.
17. **python-multipart history** — CVE-2026-40347, CVE-2026-24486 in earlier 0.0.x. Pinned 0.0.28 is clean.
18. **Vite history** — CVE-2026-39363/4/5 were dev-server-only file-disclosure issues. Production builds unaffected. Patched in 8.0.5+; pinned 8.0.13 is clean.

## Bootstrap dependency manifests

### `pyproject.toml` (excerpt — full file lands in Commit A)

```toml
[project]
name = "target-workspace"
requires-python = ">=3.13"
dependencies = [
    "fastapi==0.136.1",
    "uvicorn[standard]==0.47.0",
    "starlette>=1.0.0,<1.1.0",
    "pydantic==2.13.4",
    "pydantic-settings==2.14.1",
    "sqlmodel==0.0.38",
    "SQLAlchemy>=2.0.49,<2.1",
    "alembic>=1.18.4,<1.19",
    "bcrypt==5.0.0",
    "Authlib==1.7.2",
    "structlog>=25.5.0,<26",
    "python-multipart==0.0.28",
    "cryptography>=48.0.0,<49",
    "pytak==7.2.1",
    "takproto==3.0.1",
    "opentelemetry-api>=1.41.1,<1.42",
    "opentelemetry-sdk>=1.41.1,<1.42",
    "opentelemetry-exporter-otlp>=1.41.1,<1.42",
    "opentelemetry-instrumentation-fastapi==0.62b1",
    "opentelemetry-instrumentation-sqlalchemy==0.62b1",
]

[dependency-groups]
dev = [
    "pytest>=9.0.3,<10",
    "pytest-asyncio>=1.3.0,<2",
    "pytest-cov>=7.1.0,<8",
    "pytest-xdist>=3.8.0,<4",
    "pytest-watcher>=0.6.3,<1",
    "hypothesis>=6.152.7,<7",
    "httpx==0.28.1",
    "polyfactory>=3.3.0,<4",
    "testcontainers>=4.14.2,<5",
    "mutmut>=3.5.0,<4",
    "diff-cover>=10.2.0,<11",
    "ruff>=0.15.12,<0.16",
    "mypy>=2.1.0,<3",
    "bandit[toml]>=1.9.4,<2",
    "detect-secrets==1.5.0",
    "pip-audit>=2.10.0,<3",
    "pip-licenses>=5.0,<6",
    "pre-commit>=4.6.0,<5",
    "commitizen>=4.16.0,<5",
]
```

### `frontend/package.json` (excerpt)

```json
{
  "dependencies": {
    "react": "19.2.6",
    "react-dom": "19.2.6",
    "@cesium/engine": "24.0.0",
    "@cesium/widgets": "14.0.0",
    "resium": "1.20.0",
    "@tanstack/react-query": "5.100.10",
    "zustand": "5.0.13"
  },
  "devDependencies": {
    "@types/react": "19.2.14",
    "@types/react-dom": "19.2.3",
    "typescript": "6.0.3",
    "vite": "8.0.13",
    "tailwindcss": "4.3.0",
    "shadcn": "4.7.0"
  }
}
```

## Re-audit cadence

This manifest is a snapshot. Schedule:
- **Weekly** — Dependabot opens PRs; CI gates (pip-audit, license check, Trivy scan) verify each upgrade.
- **Monthly** — manual re-audit of this document against OSV.dev and GHSA for any component, even when no PR landed.
- **Quarterly** — review the "stale velocity" call-outs (detect-secrets, httpx) for alternatives.
- **On incident** — when a supply-chain incident hits any pinned component (StepSecurity advisory, GitHub advisory), pause builds, audit the pin, regenerate the lockfile.

## Sources cited

(Full bibliography preserved in `/tmp/stack_audit.md` from the audit run; key URLs below.)

- https://www.python.org/downloads/release/python-31313/
- https://pypi.org/project/fastapi/
- https://github.com/Kludex/starlette/releases
- https://docs.authlib.org/en/latest/community/security.html
- https://github.com/pyca/cryptography/blob/main/CHANGELOG.rst
- https://pypi.org/project/pytak/
- https://github.com/vitejs/vite/releases
- https://www.npmjs.com/package/@cesium/engine
- https://github.com/aquasecurity/trivy/discussions/10425
- https://www.stepsecurity.io/blog/trivy-compromised-a-second-time---malicious-v0-69-4-release
- https://images.chainguard.dev/directory/image/python/overview
- https://www.postgresql.org/about/news/postgresql-184-1710-1614-1518-and-1423-released-3297/
- https://www.sqlite.org/cves.html
- https://osv.dev/
- https://github.com/advisories
- https://nvd.nist.gov/
