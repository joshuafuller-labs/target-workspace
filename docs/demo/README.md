# Animated walkthrough (tw-4ty)

Self-contained demo recording — Kerr County flash-flood scenario, ~85 s tour. Anchored on the seeded `Incident Response · Op Period 1` board so every screen shows real card density.

## Outputs

| File | Notes |
|---|---|
| `demo-walkthrough.mp4` | **Primary deliverable.** H.264 + faststart, **captions burned into the frames** via the `subtitles` filter (libass). |
| `demo-walkthrough.webm` | Uncaptioned raw VP8 master from Playwright. Re-encoding to VP9 with burned-in captions takes ~50 CPU-min on 1080p, so the captioned variant only ships as mp4. |
| `demo-walkthrough.vtt` | Sidecar WebVTT captions for accessibility-aware platforms that prefer a separate track. |
| `demo-walkthrough.srt` | Same cues as the VTT in SRT format (what ffmpeg's `subtitles` filter consumes). |
| `walkthrough-steps.json` | Step-timing JSON the caption builder produces; regenerated each run. |
| `raw/` | Per-run Playwright artifacts (videos, error-context). Not committed. |

## Story arc

1. Login → kanban
2. Switch to `Incident Response · Op Period 1` (Kerr County)
3. Pan the full kanban — welfare checks, hazards, SAR tasks, in-progress rescues
4. Highlight hazard styling on the LWX-2207 card
5. Open `MISSING-001` (the dedup of WC-MISSING-001a/b)
6. TargetDetail — audit chain, observation timeline, live positions
7. `/audit` — filter to `auth.login.success`, demonstrate the table + CSV export
8. `/settings` — General tab, brand-name input
9. Close on the kanban

## Regenerate

The app stack must be reachable at `http://127.0.0.1:8000` with the default admin (`admin@example.com` / `demopw` from `docker/docker-compose.yml`).

```bash
docker compose -f docker/docker-compose.yml up -d --build
cd frontend
bash scripts/record-demo.sh
```

The script:

1. Runs the Playwright spec at `tests/demo/walkthrough.spec.ts`.
2. Walks the step-timing JSON through `scripts/build-captions.mjs` to produce the VTT.
3. Converts VTT → SRT.
4. Re-encodes the raw webm to mp4 with the SRT burned in via ffmpeg's `subtitles` filter (libass).

Total wall time: ~2 minutes.

## Editing the narration

`tests/demo/walkthrough.spec.ts` carries the script. Each `narrate(page, "…", dwell_ms)` call adds a caption cue *and* waits `dwell_ms` milliseconds; the cue start/end timestamps are computed from when the call fires relative to `page.goto("/")`. Changing prose or pacing means re-running `record-demo.sh` — captions and video must regenerate together so they stay in sync.

## Caption styling

ffmpeg's `subtitles=` filter accepts an ASS `force_style` string. The defaults in `scripts/record-demo.sh`:

- `FontName=DejaVu Sans` — readable across dark/light frames
- `Fontsize=22`
- White text on a semi-opaque black box (`BorderStyle=4`)
- `MarginV=60` to sit clear of the bottom edge

Tweak in `record-demo.sh`; rerun to see the change.

## CI

Out of scope. Recording is a manual step before tagging a release. Ship `.mp4` + `.vtt` together so platforms with caption-track support can use the VTT and everyone else gets the burned-in version.
