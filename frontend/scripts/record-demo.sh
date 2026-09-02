#!/usr/bin/env bash
#
# Animated walkthrough recorder (tw-4ty).
#
# Pre-conditions:
#   - The app stack is reachable at http://127.0.0.1:8000 (e.g. via
#     `docker compose -f docker/docker-compose.yml up -d`).
#   - The admin account in TW_ADMIN_EMAIL / TW_ADMIN_PASSWORD lines
#     up with what walkthrough.spec.ts uses (admin@example.com /
#     demopw by default).
#
# Outputs (all under ../docs/demo/):
#   raw/.../*.webm                    — Playwright-recorded video
#   demo-walkthrough.webm             — re-encoded master
#   demo-walkthrough.mp4              — compatibility encode
#   demo-walkthrough.vtt              — synchronized closed captions
#
# Idempotent: re-running overwrites the docs/demo/ outputs.

set -euo pipefail

cd "$(dirname "$0")/.."

OUT_DIR="../docs/demo"
RAW_DIR="$OUT_DIR/raw"

mkdir -p "$OUT_DIR" "$RAW_DIR"

echo "[record-demo] preflight — checking app stack…"
if ! curl -sf http://127.0.0.1:8000/healthz >/dev/null; then
  echo "[record-demo] ERROR: app stack not healthy at http://127.0.0.1:8000" >&2
  echo "  start it with: docker compose -f docker/docker-compose.yml up -d" >&2
  exit 1
fi

echo "[record-demo] running Playwright recording…"
# Playwright writes video + the step-timing attachment into outputDir
# (../docs/demo/raw per playwright.demo.config.ts). The directory is
# cleared first so each run produces a clean set.
rm -rf "$RAW_DIR"
mkdir -p "$RAW_DIR"
npx playwright test --config=playwright.demo.config.ts

# Locate the recorded video (Playwright nests it under a hashed dir).
WEBM_SRC=$(find "$RAW_DIR" -name '*.webm' -print -quit || true)
if [[ -z "$WEBM_SRC" ]]; then
  echo "[record-demo] ERROR: no webm produced under $RAW_DIR" >&2
  exit 1
fi

# Locate the step-timing JSON the spec writes to docs/demo/ root.
STEPS_JSON="$OUT_DIR/walkthrough-steps.json"
if [[ ! -f "$STEPS_JSON" ]]; then
  STEPS_JSON=""
fi

echo "[record-demo] re-encoding to docs/demo/ …"
cp "$WEBM_SRC" "$OUT_DIR/demo-walkthrough.raw.webm"

if [[ -n "$STEPS_JSON" ]]; then
  echo "[record-demo] building captions…"
  node scripts/build-captions.mjs "$STEPS_JSON" "$OUT_DIR/demo-walkthrough.vtt"
  # Convert VTT → SRT. Strip the VTT header line, drop NOTE blocks
  # entirely (header + body up to the next blank line), and rewrite
  # the millisecond separator from . to ,.
  python3 - "$OUT_DIR/demo-walkthrough.vtt" "$OUT_DIR/demo-walkthrough.srt" <<'PY'
import sys, re, pathlib
src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
lines = src.read_text().splitlines()
out = []
skip_note = False
for line in lines:
    if line == "WEBVTT":
        continue
    if line.startswith("NOTE"):
        skip_note = True
        continue
    if skip_note:
        if line.strip() == "":
            skip_note = False
        continue
    line = re.sub(
        r"(\d{2}:\d{2}:\d{2})\.(\d{3})",
        lambda m: m.group(1) + "," + m.group(2),
        line,
    )
    out.append(line)
dst.write_text("\n".join(out).strip() + "\n")
PY

  echo "[record-demo] burning captions into video…"
  # Burn captions onto the master webm via the subtitles filter, then
  # produce both web-friendly encodes from the captioned source. The
  # subtitles filter requires libass; force_style controls placement
  # and readability against the SPA's dark UI. Absolute paths because
  # libass resolves relative paths from its own working dir, not the
  # ffmpeg invocation's.
  ABS_RAW=$(readlink -f "$OUT_DIR/demo-walkthrough.raw.webm")
  ABS_SRT=$(readlink -f "$OUT_DIR/demo-walkthrough.srt")
  ABS_MP4=$(readlink -f "$OUT_DIR/demo-walkthrough.mp4" || echo "$(readlink -f "$OUT_DIR")/demo-walkthrough.mp4")
  ABS_WEBM=$(readlink -f "$OUT_DIR/demo-walkthrough.webm" || echo "$(readlink -f "$OUT_DIR")/demo-walkthrough.webm")
  SUBS_STYLE="FontName=DejaVu Sans,Fontsize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H80000000,BorderStyle=4,Outline=1,Shadow=0,MarginV=60"
  ffmpeg -y -loglevel warning \
    -i "$ABS_RAW" \
    -vf "subtitles='$ABS_SRT':force_style='$SUBS_STYLE'" \
    -c:v libx264 -preset slow -crf 22 \
    -pix_fmt yuv420p \
    -movflags +faststart \
    -an \
    "$ABS_MP4"
  # webm output is the un-captioned raw recording — re-encoding to VP9
  # with subtitles burned in took ~50 CPU-min on 1080p with default
  # settings. The mp4 is the primary deliverable; the .raw webm stays
  # in place as a no-caption alternative.
  cp "$ABS_RAW" "$ABS_WEBM"
else
  echo "[record-demo] WARNING: no walkthrough-steps.json — captions skipped" >&2
  cp "$OUT_DIR/demo-walkthrough.raw.webm" "$OUT_DIR/demo-walkthrough.webm"
  ffmpeg -y -loglevel warning \
    -i "$OUT_DIR/demo-walkthrough.webm" \
    -c:v libx264 -preset slow -crf 22 \
    -pix_fmt yuv420p \
    -movflags +faststart \
    -an \
    "$OUT_DIR/demo-walkthrough.mp4"
fi

# Drop the un-captioned master; we keep the burned-in webm + mp4 only.
rm -f "$OUT_DIR/demo-walkthrough.raw.webm"

echo "[record-demo] done."
echo "  outputs:"
ls -lh "$OUT_DIR"/demo-walkthrough.* 2>/dev/null || true
