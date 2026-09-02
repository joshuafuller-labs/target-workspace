# ADR 0002 — Backend stack: Python 3.13+ on FastAPI

**Status:** Accepted
**Date:** 2026-05-16

## Context

This is a CoT-router-with-kanban-on-top. The workload is I/O-bound (HTTP, WebSocket fan-out, SQL, socket I/O for CoT), not CPU-bound. Plugin discoverability is the product's load-bearing feature per [ADR 0008](0008-malleability-principle.md). Solo developer needs maximum velocity. Tabled-license posture requires permissively-licensed deps only.

Candidates considered: Python+FastAPI, Go, Rust, TypeScript/Node.

## Decision

Python 3.13+ with FastAPI as the backend. Specifically:

- **FastAPI** (MIT) — OpenAPI emerges from type hints; async-first; best Pydantic integration
- **Pydantic 2.x** (MIT) — typed data model, schema generation
- **SQLModel** (MIT) — unified ORM/API model
- **SQLAlchemy 2.0** + **Alembic** for the DB layer
- **uv** (Astral, Apache-2.0/MIT) for dependency management
- **`importlib.metadata.entry_points`** for plugin discovery (stdlib)

Full pinned manifest in [docs/tech-stack.md](../tech-stack.md).

## Consequences

**Wins:**
- `pytak` (Apache-2.0) is the gold-standard CoT library; we stand on it
- AI/CV/OSINT adapter ecosystem is Python-native if/when those land
- Plugin model is `uv pip install target-workspace-source-mqtt` — production-grade, not invented
- Solo-dev velocity highest of the candidates
- Zero copyleft introduced in application code

**Trade-offs accepted:**
- Python is slower than Go/Rust on CPU-bound workloads. **Mitigation:** workload is I/O-bound; if profiling ever shows a hot path, rewrite that piece in Rust via PyO3 (the Pydantic v2, Polars, ruff, uv pattern). Pay perf cost only where measured to matter.
- Type safety is weaker than Rust/Go. **Mitigation:** `mypy --strict` is non-negotiable; failing CI on any untyped def.
- Memory footprint is higher than Go. **Mitigation:** acceptable for the deploy scale; revisit if container-density becomes a concern.

**Rejected alternatives:**
- **Go**: weaker CoT lib ecosystem (`goatak` is the only mature option, ~150 stars vs `pytak` ~600); Go plugins fundamentally cannot match `pip install` for adapter distribution without significant infrastructure (HashiCorp gRPC plugin model, WASM, or recompile-to-add); slower solo-dev pace.
- **Rust**: too far for solo MVP; no mature CoT lib; would need to write CoT plumbing from scratch.
- **TypeScript/Node**: same-language-as-frontend appeal, but `node-cot` ecosystem is smaller than `pytak`, and nothing in TS matches FastAPI's "OpenAPI emerges from your types" elegance.

## References

- [docs/tech-stack.md](../tech-stack.md) — pinned versions and CVE audit
- [docs/foundation.md](../foundation.md) — full foundation enumeration
- [ADR 0013 — API client-agnostic](0013-api-client-agnostic.md) — FastAPI is the implementation; the API surface contract has its own constraints
