# ADR 0004 — CesiumJS map pane is in MVP scope

**Status:** Accepted
**Date:** 2026-05-16

## Context

Defense/IC operators expect 3D geospatial fidelity. CesiumJS powers WebTAK and many DoD COP UIs. An MVP without a globe risks failing the first 30-second demo for the persona we're anchoring to.

## Decision

CesiumJS is in MVP scope as the map pane. Specifically:
- **`@cesium/engine` 24.0** + **`@cesium/widgets` 14.0** (Apache-2.0) — the modern split-package model
- **Resium 1.20** for React bindings (MIT)
- **Tile source default:** bundled offline Natural Earth + workspace-configurable override (Cesium ion, self-hosted TMS/WMS, Mapbox token, etc.) — preserves airgap-friendliness while letting operators upgrade fidelity
- **2D / 3D toggle** ships at MVP (Cesium supports both natively)

## Consequences

**Wins:**
- The 30-second demo lands with credibility
- Apache-2.0 license fits the no-copyleft constraint
- Tile source is configurable per workspace, satisfying the malleability principle ([ADR 0008](0008-malleability-principle.md))
- Hobbyist gets a working globe from `docker run` with no third-party signup; production operators point at their TMS / Cesium ion enterprise

**Trade-offs accepted:**
- CesiumJS is ~6MB; mitigated by Vite `manualChunks` separating it from the app shell
- Tile source decisions add a sub-axis of customization (and a small documentation burden)
- Bundled offline tiles add ~50-200MB to the container image

## References

- https://cesium.com/learn/cesiumjs/ref-doc/
- [docs/foundation.md](../foundation.md)
