#!/usr/bin/env bash
# Assemble every episode whose narration is COMPLETE, in whatever order they
# become ready.
#
# assemble-all.sh walks the publish queue in rank order and blocks on each
# episode until its narration finishes. That is correct for publishing, but wrong
# for rendering: it left four fully-voiced episodes idle while waiting on one that
# had not started. Render order does not matter - publish order is decided later,
# from research/publish_order.json. So take whatever is ready.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
PY=.venv/bin/python
LOCK="renders/.assemble-ready.lock"
mkdir "$LOCK" 2>/dev/null || { echo "another assembler holds $LOCK"; exit 0; }
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

# Preflight. tests/test_caption_burn.py needs real wavs and real clips, so CI
# cannot run it - this machine can, and this is the script that burns captions
# into finished episodes. Running it here is what stops it being a test nothing
# invokes. It hard-fails if it examines zero frames.
echo "preflight: tests/test_caption_burn.py"
if ! $PY tests/test_caption_burn.py; then
  echo "STOP: the caption burn is not behaving; refusing to render episodes"
  exit 2
fi

n=0
while :; do
  progressed=0
  for plan in plans/*.json; do
    slug=$(basename "$plan" .json)
    out="renders/${slug}-final.mp4"
    [ -s "$out" ] && continue
    want=$($PY -c "import json;print(len(json.load(open('$plan'))))" 2>/dev/null)
    have=$(find "audio/$slug" -name '*.wav' 2>/dev/null | wc -l | tr -d ' ')
    # Exact match only. assemble.py muxes audio ONLY when beats == plan segments;
    # a short directory yields a SILENT video rather than an error.
    [ -z "$want" ] || [ "$have" -lt "$want" ] && continue
    echo "ASSEMBLING $slug ($have/$want)"
    # --burn-captions is safe here BY CONSTRUCTION: this loop only reaches an
    # episode whose wav count equals its beat count, and assemble.py refuses to
    # burn anything whose cue timing is not measured. Passing it is what makes
    # the burn live rather than a flag nobody invokes.
    if $PY visuals/assemble.py "$plan" "$out" --audio-dir "audio/$slug" \
         --burn-captions >"/tmp/claude-501/asm-$slug.log" 2>&1; then
      echo "OK $out"; n=$((n+1)); progressed=1
    else
      echo "FAIL $slug - see /tmp/claude-501/asm-$slug.log"
    fi
  done
  # Nothing ready this pass. If narration is still running more will arrive;
  # if it has stopped, everything assemblable is assembled and we are done.
  if [ "$progressed" -eq 0 ]; then
    pgrep -f narrate_all.py >/dev/null || break
    sleep 120
  fi
done
echo "---"; echo "assembled this run: $n"
