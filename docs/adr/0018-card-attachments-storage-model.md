# ADR 0018 — Card attachments: storage model

Status: Accepted (provisional — flagged for user review).

## Context

`tw-b43` (Attachment refs) shipped the simplest possible attachment model — append `{url, sha256, kind, media_type, caption}` records onto `target.custom_fields["attachments"]`. That works for citation links and externally-hosted imagery, but `tw-0um3` flagged the unaddressed depth in the disaster-ops / intel / federation use-cases:

- Door-to-door damage assessment photos, FEMA PDA forms, drone imagery, voice memos from field teams.
- CV/AI provenance imagery; sensor screenshots; cite-and-redirect to articles.
- ATAK Mission Package shared content; voice notes captured in flight.

Eight design questions were filed against the exploration ticket. This ADR answers them so the eventual implementation bd has firm scope.

## Decisions

### 1. Storage backend

**Reference-only.** File bytes live outside the database: a configurable storage adapter (filesystem at MVP, S3-compatible behind the same interface in v1.x). The DB holds only the metadata row + content hash.

Reason: target rows are small and frequently fanned out via realtime; bundling multi-MB blobs into row state would balloon WebSocket frames, snapshots, and federation slices.

### 2. Content addressing

**SHA-256, mandatory on the metadata row.** The hash is also the stored filename (sharded `aa/bb/<hash>.bin`) so dedupe is automatic across workspaces and tamper detection is one re-hash away.

Voice memos and other non-imagery follow the same pattern. The metadata row carries `media_type` for client-side rendering.

### 3. Per-workspace isolation + ACL

Two layers:

- **Path isolation**: storage adapter prefixes by `workspace_id` so even if two workspaces hash-collide they cannot read each other's bytes.
- **Access control**: inherited from the parent target. RBAC on `target_id` already covers "who can see this card"; the attachment metadata row carries the parent target_id so the same check applies. No per-attachment ACL at MVP — adds surface area without a customer pulling for it.

### 4. EXIF stripping

**Strip on upload, irreversibly.** Default-on with a per-workspace override. The risk model: cross-org sharing where embedded GPS or device IDs leak the source. Stripped at the storage adapter; the original is not retained.

Carve-out: ops teams that *need* EXIF (forensics, incident reconstruction) flip the workspace toggle off; the SPA shows a "EXIF retained" badge on every upload while that toggle is off so it can't silently regress.

### 5. Thumbnails

**Generated lazily.** First read for a given size produces and caches a thumbnail next to the original (`aa/bb/<hash>.thumb.<size>.jpg`). Sizes are a fixed allowlist (`128`, `512`, `2048`) — not arbitrary — so callers can't fill disk with stamp-collection sizes.

PDF first-page + video keyframe are post-MVP. At MVP, non-image attachments render a file-type icon.

### 6. Antivirus

**Out of band.** A `clamav` (or equivalent) scan hook runs against the storage path on a worker; metadata row carries `scan_status ∈ {pending, clean, infected, error}`. Attachments with `status != clean` are inaccessible from the SPA. Scan failures fall to `error`; admin alerts but doesn't auto-delete.

Reason: scan-on-request blocks the upload path and breaks the field-team "snap and go" UX; the disconnected mobile scenario can't afford that round-trip anyway.

### 7. Retention / TTL

**Per-workspace policy, default infinite.** Disaster operations want post-incident retention for after-action review and FOIA / Public Records Act response. Intel use-cases occasionally want hot-storage aging to cold. Policy lives on the workspace row; the deletion sweep is a periodic job (post-MVP).

The metadata row carries `expires_at`; sweep deletes bytes and rows past TTL atomically.

### 8. Federation

**Hash-list-then-pull.** Federation slices include the attachment metadata row (hash + media_type + bytes-size + caption) but never the bytes. Receiving peer requests bytes only when a client view actually needs them (`GET /v1/federation/blob/<hash>`). Bandwidth-aware; aligns with the federation slice envelope from ADR 0016.

Receiving peer caches pulled bytes locally; cache eviction is its own policy.

### 9. CoT-out (ATAK Mission Package)

A future CoT-out publisher can package referenced attachments into a `.zip` Mission Package, alongside the CoT XML. Not in MVP — flagged as `cot.outbound.mission-package` follow-up.

## Implementation bd

When ready to ship, file a concrete implementation ticket that:

- Migrates `attachment` to its own table (`attachment(id, workspace_id, target_id, sha256, media_type, bytes_size, caption, exif_retained, scan_status, expires_at, created_at)`).
- Keeps the existing `custom_fields["attachments"]` shape as a read-only compatibility view for tw-b43 callers.
- Introduces `storage_adapter` interface with `local_fs` implementation; `s3` in v1.x.
- Wires the upload path through the EXIF stripper.
- Adds the lazy thumbnail handler at `GET /v1/attachments/<hash>/thumb/<size>`.

The implementation ticket should NOT bundle antivirus, federation, or CoT-out — those are independent follow-ups.

## Consequences

- Attachment ergonomics improve substantially without dragging in S3 dep at MVP.
- We keep the door open to S3 / federation / antivirus by writing against a thin storage interface.
- Old `tw-b43` URL+hash references continue to work; the new table is the canonical write path going forward.
- Disaster-ops field photo flow becomes a snap-and-attach UX rather than "fight with an external image host."

## Open questions deferred to implementation

- Multipart-resume for large field uploads on flaky LTE. (Probably worth doing in v1.x; field interviews will say.)
- End-to-end encryption for cross-peer attachment sync. Currently the federation slice is signed but not encrypted; bytes-at-rest encryption per-peer is a v1.x compliance-driven extension.
