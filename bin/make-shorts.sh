#!/usr/bin/env bash
#
# make-shorts.sh - cut YouTube Shorts from finished episodes.
#
#   bin/make-shorts.sh                       # the retrofit set, 1 Short each
#   bin/make-shorts.sh --count 3             # the retrofit set, up to 3 each
#   bin/make-shorts.sh --all --count 2       # every episode with a -final.mp4
#   bin/make-shorts.sh --dry-run 05          # show the beat pick, render nothing
#   bin/make-shorts.sh 05 10                 # named episodes (prefix or full slug)
#
# Output: shorts/<slug>-short.mp4 (1080x1920, under 60s, burned-in captions,
# audio taken verbatim from audio/<slug>/*.wav - never regenerated).
#
# WHAT THIS DOES NOT DO, and it matters
# -------------------------------------
# It reframes a finished 16:9 render; it does not re-render vertically. The
# 1920x1080 picture has its burned caption band cropped off the bottom (782 of
# 1080 rows survive where a two-line cue occurs) and what is left becomes a
# 1080x440 band; the rest of the 1080x1920 canvas is wordmark, blurred fill, the
# redrawn source credit, and this module's own captions. That is the correct call
# while visuals/design.py is fixed at 1920x1080 - a centre crop would behead the
# two-column layouts - but it is a reframe, not a native vertical design, and the
# crop costs 168 rows of picture against an uncropped scale. If Shorts become the
# primary lane, the next step is a vertical render path in the visuals system,
# not a better crop. See the header of visuals/shorts.py.
#
# ATTRIBUTION. The crop takes the source credit with it (segments_species.py
# draws it at row 975, footage.py at 991-1038, both below the caption plate that
# ends at 962). shorts.py re-reads that credit from channel/imagery/rights.json
# and channel/imagery/video_rights.json and redraws it under the band, and drops
# any beat whose credit it cannot resolve. loop/validate.py V14 reads it back off
# the finished pixels; V15 proves the caption band really went.
#
set -euo pipefail

cd "$(dirname "$0")/.."
PY=./.venv/bin/python
[ -x "$PY" ] || { echo "FAIL: no venv at $PY" >&2; exit 1; }
command -v ffmpeg >/dev/null || { echo "FAIL: ffmpeg not on PATH" >&2; exit 1; }

# Publish order. These four are the retrofit set: 2, 3 and 4 are unpublished and
# 1 went live with no views, so all four can be re-uploaded cheaply.
DEFAULT_SLUGS=(
  10-what-is-the-deepest-part-of-the-ocean
  05-why-many-deep-sea-creatures-are-red
  01-why-deep-sea-creatures-look-so-weird
  14-how-big-is-a-colossal-squid
)

ARGS=()
ARGS+=()  # keep set -u happy when no flags are passed
SLUGS=()
ALL=0
for a in "$@"; do
  case "$a" in
    --all) ALL=1 ;;
    -*)    ARGS+=("$a") ;;
    *)     if [[ "${#ARGS[@]}" -gt 0 && "${ARGS[@]: -1}" == "--count" ]]; then
             ARGS+=("$a")
           else
             SLUGS+=("$a")
           fi ;;
  esac
done

if [ "$ALL" -eq 1 ]; then
  while IFS= read -r f; do
    SLUGS+=("$(basename "$f" -final.mp4)")
  done < <(ls -1 renders/*-final.mp4 2>/dev/null || true)
elif [ "${#SLUGS[@]}" -eq 0 ]; then
  SLUGS=("${DEFAULT_SLUGS[@]}")
fi

# Resolve a bare prefix ("05") to the full slug, and drop anything with no
# finished render - but never silently drop everything.
RESOLVED=()
for s in "${SLUGS[@]}"; do
  match=$(ls -1 "renders/${s}"*-final.mp4 2>/dev/null | head -1 || true)
  if [ -z "$match" ]; then
    echo "skip: no renders/${s}*-final.mp4" >&2
    continue
  fi
  RESOLVED+=("$(basename "$match" -final.mp4)")
done

# Rule 0: no stage may exit 0 having done nothing.
if [ "${#RESOLVED[@]}" -eq 0 ]; then
  echo "FAIL: empty input set - no finished -final.mp4 render matched. Nothing made." >&2
  exit 2
fi

echo "shorts: ${#RESOLVED[@]} episode(s) -> shorts/"
mkdir -p shorts

# One episode at a time, and ffmpeg left to its own threading. The machine is 8 GB
# and a voice job may be live; stacking ffmpeg processes here buys nothing and
# risks the thing that is actually irreplaceable.
exec "$PY" visuals/shorts.py ${ARGS[@]+"${ARGS[@]}"} "${RESOLVED[@]}"
