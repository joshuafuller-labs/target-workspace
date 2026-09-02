# Mobile-primary personas

Per [ADR 0012](../adr/0012-mobile-mvp-separate-scope.md) and `docs/mobile-mvp-scope.md`, mobile is its own MVP with **sibling personas**, not derivatives of the desktop personas. These are the user profiles the mobile MVP is built for.

## P1 — Field Operator

> "I'm soaking wet at 0230, on a 4G connection that drops every 90 seconds. Get the report in and let me move."

- **Device**: personal phone (Android 14+, iOS 17+), occasionally a Toughbook tablet.
- **Network**: cell-tower at the edge of coverage; intermittent. Drops happen mid-form.
- **Lighting**: variable — bright sun, headlamp at night, vehicle dome light. UI must survive both.
- **Hands**: gloved a third of the time. Touch targets ≥ 44px non-negotiable.
- **Primary action**: capture. Title + photo + GPS in ≤ 30s.
- **Secondary action**: confirm sync afterwards.
- **What they do NOT do on mobile**: edit boards, manage users, browse audit. That's a desktop concern.

Tickets that serve this persona: `tw-bux` (capture API), `tw-2j9` (offline-sync ETag), `tw-cjk` (audit `since=` resume), `tw-45s` (offline tiles).

## P2 — Strike-Team Responder

> "We rolled in three hours ago from Tennessee. Add me to the SAR group; my access expires when we redeploy."

- **Device**: phone, sometimes their own.
- **Network**: better than P1 (they're usually at an EOC or staging area when in-app), but expects to leave and reconnect.
- **Onboarding**: the on-scene coordinator gives them a join URL via Signal or printout (`tw-qmnh` invitation flow). They tap it, set a password, they're in.
- **Access**: time-bound (`tw-6to0`). When their assignment ends, access lapses gracefully; their captures stay in the record.
- **Primary action**: capture in the field + acknowledge tasking they've been assigned.

Tickets that serve this persona: `tw-qmnh` (invitations), `tw-6to0` (expires_at), `tw-icj8` (groups).

## P3 — Public-Safety Captain (mobile-secondary)

> "I work the kanban from the EOC desktop. On the phone, all I want is to know when something I gated needs me to look again."

- **Device**: phone, secondary; their primary workstation is desktop.
- **Network**: usually good.
- **Action**: receive push, tap to view the card, acknowledge or take action.
- **What they do NOT do on mobile**: original capture (that's P1 / P2). The Captain consumes mobile push; they create on desktop.

Tickets that serve this persona: `tw-ngn5` (trigger seam — the substrate push notifications ride on), per-target ACL push subscription (post-MVP, follows from `tw-liwf`).

## Personas explicitly NOT served on mobile

These exist on desktop but have no mobile workflow:

- **Workspace Admin**: user provisioning, RBAC, theme. Desktop-only.
- **Intel Analyst**: cross-correlation, map exploration with overlays, audit trail review. Desktop-only.
- **Source Adapter Operator**: configuring HTTP webhook / CoT-in / sources. Desktop-only.

## Design implications

1. **Native back-button respect**: every screen has a real back action that mirrors browser/Android back. No "are you sure?" prompts blocking exit.
2. **Photo-first capture**: take photo → form prefills GPS + timestamp → user adds title + optional notes → submit. Default ordering is camera-led, not form-led.
3. **Sync indicator on every screen**: there is a chip in the chrome that says one of `synced` / `syncing` / `offline (N pending)` / `error`. Never hidden.
4. **No animations during capture**: motion costs latency that capture-on-flaky-network can't afford.
5. **Light + dark, high-contrast outdoor mode**: the existing themes (`docs/foundation.md` §16) need a mobile-tuned variant. Hi-vis orange + black on white for daylight; muted on dark for night.

## Open questions (for the mobile-MVP design phase)

- PWA vs React Native vs native — pending engineering capacity decision.
- Push delivery mechanism: web-push for PWA, APNs/FCM for native; the trigger seam (`tw-ngn5`) is platform-agnostic so the choice can defer.
- Authentication: device-bound session vs. service-account-style bearer (`tw-sodu`). Probably session for end-users, bearer for integrations.
