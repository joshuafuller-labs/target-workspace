# ADR 0016 — Federation transport: separate plane

Status: Accepted (provisional — flagged for user review).

## Context

`tw-a3ix` raised three options for how peer Target Workspace instances exchange data:

- **Option A — TAK piggyback.** Use shared TAK servers; federation = CoT events on the operational wire.
- **Option B — Separate plane.** Custom protocol over HTTPS/WebSocket/mesh. CoT remains the operational wire; federation control + data is its own plane.
- **Option C — Hybrid.** TAK for operational events (positions, cards); separate plane for control (auth, ACL, audit, AAR).

## Decision

**Option B, separate plane.**

Rationale:

- The federation primitive we actually need carries rich payloads: signed audit events (`tw-16c0`), ACL labels, version vectors, attachment manifests, peer-id provenance. CoT events are not the right wire format for those — they would be packaged inside CoT custom elements, which is awkward and brittle.
- TAK piggyback ties our federation lifecycle to TAK-server administrative state. If a peer's TAK server goes down or filters our traffic, our control plane fails. A separate plane is operationally independent.
- ATAK/CoT remains the operational wire (CoT-IN, CoT-OUT ride on TAK as they do today). This decision is about *control* and *audit* — not about silencing CoT.
- A hybrid would be more flexible but doubles the surface area at MVP — not justified before we have peer instances actually federating.

## Consequences

- `tw-aoo` Effector plugin contract / `tw-12l` impl remain post-MVP, separate from this decision.
- Federation transport spec — once written — should target HTTPS-with-WebSocket-upgrade for the control plane and store-and-forward semantics for delivery (peers can be intermittently online). Mesh-radio transport for the federation control plane is a v2 concern.
- `tw-16c0` signed audit events carry `peer_id` + signature exactly because cross-instance reassembly assumes a verifiable provenance chain; this ADR confirms that's the right shape.
- The `cot_out` publisher pipeline (`tw-50i5`) sits inside the operational wire, NOT the federation control plane.

## Status note

This ADR was authored autonomously during the 2026-05-18 `/goal` session per the directive to make a conservative engineering assumption when the user is unavailable. Flagged for explicit user sign-off on next session.
