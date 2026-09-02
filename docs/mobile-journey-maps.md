# Mobile MVP — Journey maps

End-to-end journey diagrams for the mobile MVP personas. Each journey corresponds to one or more user stories in [`docs/mobile-user-stories.md`](mobile-user-stories.md).

---

## Journey A — Field Operator captures a missing-person sighting (Helene-shape)

Persona: Field Operator (P1).
Trigger: Operator spots a person matching a missing-person description while clearing a flooded neighborhood.

```
1. Operator opens app
   │ (cold-launch: ≤ 3s; warm-launch: instant)
   │ Sync chip: 'synced' (cached from earlier check-in)
   ▼
2. Taps "Capture"
   │ Camera opens immediately, no preflight modal.
   ▼
3. Takes photo
   │ Photo cached; GPS sample captured silently in parallel.
   ▼
4. Form pre-fills lat/lon/time
   │ Operator types title: "F adult, mid-50s, blue jacket, 142 Oak St"
   │ Operator (optionally) types remarks.
   ▼
5. Taps Submit
   │ Sync chip flips to 'syncing 1'.
   │ Cell drops mid-request.
   │ Request requeues with backoff.
   │ Chip becomes 'offline (1 pending)'.
   ▼
6. Operator moves to next house
   │ App is closed / backgrounded.
   ▼
7. Cell returns 8 minutes later
   │ Background sync fires (App Refresh / Service Worker).
   │ Captures sync; chip flips to 'synced'.
   │ A subtle local notification: "Capture #142 synced."
```

Architectural enablers riding through this journey:
- `tw-bux` POST /v1/capture
- `tw-2j9` ETag for retry idempotency
- `tw-54t` Idempotency-Key for safe retry on the multipart upload
- `tw-cjk` audit `since=` to resume any other state on app re-foreground

Failure modes covered:
- Server 422 (board deleted between capture and sync): item lands in error tray; operator chooses replacement board, retries.
- Server 401 (session expired in background): app re-authenticates via remembered credentials; capture re-tries.
- Server 429 (rate-limit hit on a burst): item waits in queue with exponential backoff.

---

## Journey B — Strike-Team Responder onboarded mid-incident

Persona: Strike-Team Responder (P2).
Trigger: Coordinator on the ground texts the team lead a join URL.

```
1. Team lead receives URL via Signal/SMS
   │ https://workspace.example.invalid/redeem?token=<opaque>
   ▼
2. Team lead opens URL on phone
   │ Mobile app handles the deep-link.
   │ Redemption screen renders: email + display name + password.
   ▼
3. Fills form
   │ Password policy live-validates as they type (min 8, etc per tw-fn7a).
   ▼
4. Submits
   │ Account created (tw-qmnh redemption), session cookie set.
   │ Force-password-change is set (tw-4exk) but since they JUST set
   │ the password, the change-on-first-login is satisfied implicitly
   │ — open question: should redemption set must_change_password=False?
   │ Decision: keep the gate. The redeemer set a password mostly to
   │ satisfy onboarding; the next /change-password is their chance
   │ to set their real password. This is post-MVP polish.
   ▼
5. Lands on the "capture" screen
   │ A welcome banner says "You're in [Cajun Navy] until 0700 Mon."
   │ (Expiry banner from tw-6to0 + group membership from tw-icj8.)
   ▼
6. Goes to work
   │ Same capture flow as Journey A.
```

Architectural enablers:
- `tw-qmnh` invitation tokens
- `tw-4exk` force-password-change
- `tw-fn7a` password policy
- `tw-icj8` group membership at redemption time
- `tw-6to0` expires_at banner

---

## Journey C — Public-Safety Captain acknowledges a state change

Persona: Public-Safety Captain (P3).
Trigger: An assigned card transitions to "Needs Decision."

```
1. Captain is mid-meeting at the EOC
   │ Mobile app is backgrounded.
   ▼
2. State change happens on the server
   │ Operator on another shift moves a card to "Needs Decision."
   │ tw-ngn5 trigger seam fires on the audit event.
   │ Mobile-push adapter (post-MVP feature on the seam) sends a
   │ push to the Captain's registered device.
   ▼
3. Push arrives on phone
   │ Banner: "[SAR-12] needs your decision: continue search vs.
   │   transition to recovery — 0723L"
   ▼
4. Captain taps push
   │ App opens directly to the card view.
   │ Card detail shows the audit excerpt + current state + map dot.
   ▼
5. Captain taps "Acknowledge" or "Approve transition"
   │ Action posts to the server; another audit event fires.
   │ Push channel does NOT re-fire (the Captain is the actor).
```

Architectural enablers:
- `tw-ngn5` trigger seam (the substrate)
- Per-target ACL push subscription (post-MVP, follows from `tw-liwf`)
- Deep-linking via the mobile app's URL scheme (mobile-client-specific; tw-m55 territory)

Open design questions for this journey:
- Push delivery: web-push for PWA vs. APNs/FCM for native. The trigger seam is channel-agnostic.
- Do we batch multiple push events for the same card within a window? (Likely yes — operator chooses how the kanban moves, and the Captain sees ONE notification per logical decision.)
- What's the timeout on "acknowledge"? After N minutes unacknowledged, does the trigger re-fire? (Probably yes — that's the "escalation policy" feature, post-MVP.)

---

## Journey D — Field Operator works offline for 4 hours

Persona: Field Operator (P1).
Trigger: Operator works a flooded zone with no cell coverage.

```
1. Operator goes offline
   │ Captures queue locally (Journey A pattern, repeated 18 times).
   ▼
2. Four hours pass
   │ No reception. 18 captures queued. App keeps a low-frequency
   │ retry running in background.
   ▼
3. Operator returns to staging area; cell returns
   │ App auto-syncs queued captures (Journey A retry pattern).
   │ Sync chip cycles: offline → syncing 18 → synced.
   ▼
4. Operator pulls fresh state
   │ Implicit on app foreground: GET /v1/audit?since=<last_seen>
   │ Returns the events that happened on OTHER agents' shifts
   │ during the 4-hour offline period.
   │ Local state reconciled.
```

Architectural enablers:
- `tw-cjk` audit `since=` filter
- `tw-2j9` per-target ETag (lets client compare its local copy vs. server)
- `tw-45s` offline tiles (map still renders for context)

Reconciliation rules (specified here for the mobile-MVP design):
- Cards new since last_seen: insert locally.
- Cards updated since last_seen: replace local copy if server.version > local.version.
- Cards deleted since last_seen: remove locally.
- Captures still in the local outbox: NOT touched by reconciliation. They sync independently.

---

## Journey E — Captain logs in via desktop, NOT mobile

Persona: Public-Safety Captain (P3) — non-mobile case.

This is included only to make the boundary explicit:

```
Captain authors content on desktop. Mobile is consumption + acknowledge.
Mobile MVP launch criteria are NOT satisfied by authoring-on-mobile.
```

Don't build mobile authoring for Captains in v1.0.
