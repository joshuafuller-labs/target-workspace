# ADR 0013 — API is a client-agnostic public platform surface

**Status:** Accepted
**Date:** 2026-05-16

## Context

The web SPA is one of several expected API consumers. Others include a future focused mobile experience ([ADR 0012](0012-mobile-mvp-separate-scope.md)), an ATAK plugin (Java/Kotlin running on Android, talking to TAK Server *and* to Target Workspace), third-party integrators consuming the OpenAPI spec, automation scripts, and CI tooling.

Web-SPA-shaped APIs (cookie-only auth, CSRF tokens for every request, SSR coupling, opaque pagination cursors only the SPA understands, polling-based "real time") are a one-way door away from this future.

## Decision

Every API decision is designed as if the consumer might be a web SPA, a native iOS/Android app, an ATAK Java/Kotlin plugin, a Python script, a third-party integration, or a curl one-liner. If a design decision only works for one of those, it gets redesigned.

**Concrete commitments:**

- **OpenAPI 3.1** is the public contract. Spec is generated from FastAPI type hints, committed to repo, published as a build artifact on every release for plugin authors to codegen against.
- **Versioning is in the path** (`/v1/...`). Breaking changes get `/v2/...`. Both can coexist during transitions.
- **Schemas use `additionalProperties: false`** so client codegen produces strict types.
- **Auth supports multiple modes coexisting** (per ADR 0006 the auth seam is pluggable; this ADR specifies what the seam supports):
  - Session cookie for same-origin web SPA
  - Bearer JWT for mobile and plugin clients
  - Client-credentials (OAuth2) for ATAK plugin / device clients running headless
- **Pagination** — cursor-based with RFC 5988 `Link` headers and JSON cursor fields. No SPA-shaped magic params.
- **Filtering / sorting** — standardized syntax (`?filter=column.state==FINISH&sort=-time,name`).
- **Real-time updates** — WebSocket subscription endpoint as primary; SSE fallback for clients behind hostile proxies. Both available; clients pick.
- **Uploads** — multipart for browser; pre-signed-URL flow for large files / direct mobile uploads bypassing the app server.
- **CORS** — explicit allow-list, configurable; supports mobile webview origins (`capacitor://`, `tauri://`).
- **Errors** — RFC 7807 Problem Details. Same shape for every client.
- **Idempotency** — all POST endpoints accept `Idempotency-Key` header. Mobile clients on flaky networks can safely retry.

## Consequences

**Wins:**
- Any client can be built — by us or by the community — without backend changes
- ATAK plugin path is realistic from day one; a Java client codegen'd from the OpenAPI spec works
- Third-party integrations possible without bespoke endpoints
- Future mobile MVP doesn't require API rewrites

**Trade-offs accepted:**
- More upfront API design effort
- Auth seam handles three+ modes (more complex than cookie-only)
- More CORS configuration discipline
- Versioning discipline required from day 1 — but cheap insurance

**Anti-patterns this ADR explicitly forbids:**

- Endpoints that assume same-origin browser context
- CSRF tokens required even for bearer-token requests
- SPA-private response shapes (HTML fragments, JSX hydration data)
- Auth that only works in a browser session
- Real-time delivered only via long-polling because "that's what the SPA does"

## References

- [ADR 0002 — Python/FastAPI stack](0002-python-fastapi-stack.md)
- [ADR 0006 — TDD + supply-chain bar](0006-tdd-and-supply-chain-bar.md) (the auth seam discussion)
- [ADR 0012 — Mobile MVP separate scope](0012-mobile-mvp-separate-scope.md)
- Agent memory: `feedback_target_workspace_api_client_agnostic.md`
