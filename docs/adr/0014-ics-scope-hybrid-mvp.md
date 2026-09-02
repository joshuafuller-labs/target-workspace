# ADR 0014 — ICS scope: hybrid (ship the cheapest win in MVP)

Status: Accepted (provisional — flagged for user review).

## Context

The product is positioned as ICS-capable: one of the five themes is "ICS — Incident Command System / FEMA / EOC operations", seed data includes Incident-Response-shaped boards, the marketing implies public-safety utility. But the actual ICS machinery — operational periods, ICS-204/214/209 forms, position-based authority, resource roster, FEMA PDA — is all P2 / not in MVP today.

A NIMS-credentialed Incident Commander opening the tool will form an expectation from the theme in five seconds and then ask for ICS-214 within an hour. If we ship "ICS support" that's actually just a color palette, the brand promise is broken on first contact.

Three options were considered (see `tw-ed8u`):

- **Option A — Full ICS in MVP.** Operational periods + ICS-214 + ICS-shaped board template + position-based authority. Trained IC opens the tool and finds something they recognize. Significant engineering scope.
- **Option B — Theme-only at MVP.** Marketing matches: "ICS workflow support arrives in v1.1." Cheapest. Brand-promise risk.
- **Option C — Hybrid.** Ship the absolute cheapest ICS win: ICS-214 Activity Log export from the existing audit log. Operational periods and position-based authority defer to v1.1. Reads as "we know ICS matters, here's one concrete artifact."

## Decision

**Option C, hybrid.** ICS-214 export ships in MVP (`tw-vem9`). Operational periods (`tw-eebq`), position-based authority (`tw-l40z`), resource roster (`tw-qkp`), FEMA PDA (`tw-fgz`), full ICS-204/209 (`tw-5hq`) stay post-MVP under the `tw-13il` epic.

Rationale:

- The audit log data is already there; ICS-214 is templated generation on top.
- One concrete form per op-period is enough to make the tool defensible in conversation with a public-safety adopter. Op-periods themselves can be modeled lightly at the form-export layer (start/end timestamps as query parameters) rather than requiring a new op_period table at MVP.
- Operational-period awareness as a first-class concept is a deep schema change (`tw-eebq` description) that risks pulling in position auth (`tw-l40z`), resource entities (`tw-auf`), and incident-type classification. Deferring to v1.1 lets the MVP launch ship.

## Consequences

- `tw-vem9` is promoted into MVP (gets the `mvp` label, joins `tw-kdx1` as a direct child).
- `tw-eebq`, `tw-l40z`, `tw-qkp`, `tw-fgz`, `tw-5hq`, `tw-zkki` stay under `tw-13il` epic, post-MVP.
- The `tw-13il` epic itself remains visible from `tw-kdx1` so the question stays accountable, but its `mvp` association is conditional on this decision (it gets removed; only `tw-vem9` carries the `mvp` label out of the ICS cohort).
- Marketing copy should be calibrated: "ICS workflow support in v1.1; ICS-214 activity log generation available now."

## Status note

This ADR was authored autonomously during the 2026-05-18 `/goal` session per the directive to make a conservative engineering assumption when the user is unavailable. Flagged for explicit user sign-off on next session.
