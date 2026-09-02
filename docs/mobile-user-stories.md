# Mobile MVP — User stories & acceptance criteria

Per [`docs/mobile-mvp-scope.md`](mobile-mvp-scope.md) and [`docs/personas/mobile.md`](personas/mobile.md).

Format: **As a [persona], I [action] so that [outcome]** + concrete acceptance bullets.

---

## US-M1 — Capture an observation

**As a Field Operator, I capture a target observation with a photo and GPS so that the EOC has a verifiable record before I move to the next site.**

Acceptance:
- Tap "Capture" → camera opens; on shutter, photo is held in app memory + GPS sample is taken.
- Form pre-fills `lat`, `lon`, `time`. Operator only fills `title`. `remarks` is optional.
- Submit button is enabled even when offline.
- Submit POSTs to `/v1/capture` (multipart) per `tw-bux`.
- Offline: queue the request locally; sync indicator shows `1 pending`.
- On reconnect: request is sent within 5 seconds.
- If the server returns 422 (e.g., the chosen board was deleted), the queued item is moved to an "errors" tray with the reason; operator can re-target the board and retry.
- Whole flow completes in ≤ 30 seconds from app open → server accepts.

## US-M2 — See sync state

**As a Field Operator, I see at a glance whether my recent captures have synced so that I know whether to retry or move on.**

Acceptance:
- Chrome chip on every screen reads exactly one of: `synced` (green), `syncing N` (animated, count of in-flight), `offline (N pending)` (yellow), `error (N stuck)` (red, tappable).
- Chip is visible without horizontal scroll. Always-on; no hiding.
- Tapping the chip opens the sync tray (last 20 outgoing requests + state).

## US-M3 — Receive a push on state change

**As a Public-Safety Captain on mobile, I get a push when a card I'm assigned to changes state so that I can acknowledge or escalate without checking the app.**

Acceptance:
- Push channel registration on first launch; user opts in.
- Server emits the trigger via `tw-ngn5` on the relevant audit event; mobile-push adapter (post-MVP feature on the trigger seam) sends to the registered device.
- Tapping the push deep-links to the card view in the mobile app.
- If the user has the app open when the change happens, they get an in-app banner instead of a system push (no double-notify).

## US-M4 — Be onboarded via an invitation URL

**As a Strike-Team Responder, I tap a URL from a coordinator, set my password, and I'm in — without anyone in Buncombe IT touching my account.**

Acceptance:
- The invitation URL (from `tw-qmnh`) opens the mobile app's redemption page.
- User fills email + display name + password + retypes password.
- Password policy enforced (`tw-fn7a` server-side; client mirrors with live feedback).
- On submit: account is created, session cookie is set, user is logged in to the mobile chrome.
- First navigation prompts a force-password-change (per `tw-4exk`).
- Group membership (if the invite was scoped) is automatic via the redemption.

## US-M5 — Have my access expire gracefully

**As a Strike-Team Responder, my access lapses cleanly when my assignment ends.**

Acceptance:
- `user.expires_at` (`tw-6to0`) is set by the on-scene coordinator at issue time.
- 24 hours before expiry, mobile app shows an inline banner: "Access expires in 23h 47m."
- At expiry, the next request returns 401 `access expired`. Mobile app shows a clear "Access ended" screen with contact info for the coordinator.
- Captures already submitted remain in the record.
- Captures in the local queue are flagged in the sync tray as "blocked — access expired."

## US-M6 — Resume after offline

**As a Field Operator, after 4 hours offline I open the app and see only what changed since I disconnected, without redownloading everything.**

Acceptance:
- App tracks the last-seen audit `occurred_at` per session.
- On reconnect: `GET /v1/audit?since=<that-iso>` (`tw-cjk`) returns the delta.
- Local state is reconciled — new cards appear, stale cards refresh, deleted cards disappear.
- Reconciliation completes in ≤ 10 seconds on a 1 Mbps connection for a typical 1-day delta (assuming <500 events).

## US-M7 — Use a stable map even with no connectivity

**As a Field Operator, the basemap renders even with zero connectivity so I can point at where I am.**

Acceptance:
- Bundled Natural Earth tile pyramid ships with the mobile app (`tw-45s` override mechanism on the backend).
- Online: app prefers fresh tiles from the configured `tile_url`; offline falls back to bundled.
- Lat/lon dot for current GPS is always rendered on top.
- Map gestures: pinch zoom, pan. No 3D, no overlays.

## US-M8 — Capture under bad conditions

**As a Field Operator, the app survives one-handed, gloved-hand, sun-glare conditions.**

Acceptance:
- Every interactive element ≥ 44px touch target.
- "Capture" primary action is reachable with the thumb in one-handed mode on a 6.7" device.
- Hi-vis outdoor color scheme available (toggle in settings, or auto-detected via ambient light when permitted).
- No hover-only affordances anywhere.

---

## Out-of-MVP user stories (filed for tracking, not for v1.0)

- US-M9 (post-MVP): Voice-to-text capture for hands-free observation entry.
- US-M10 (post-MVP): Native back-camera barcode/QR scan to bind a target to a physical asset.
- US-M11 (post-MVP): Bluetooth beacon proximity for auto-correlation with nearby PLI.
- US-M12 (post-MVP): Background location collection (privacy-controlled per `tw-8h56`).
