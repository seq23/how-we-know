#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
COUNT=${VIDEO_COUNT:-20}
python "$ROOT/production/automation/validate_human_pass.py" --count "$COUNT"
mkdir -p "$ROOT/production/audio/narration" "$ROOT/production/outputs"
count=0
for script in "$ROOT"/production/scripts/plaintext/*.txt; do
  count=$((count+1)); [[ "$count" -le "$COUNT" ]] || break
  base=$(basename "$script" .txt)
  n=${base%%-*}; idx=$((10#$n)); music=$(printf "%s/production/audio/music/ambient-%02d.m4a" "$ROOT" "$(( (idx-1)%4+1 ))")
  wav="$ROOT/production/audio/narration/$base.wav"; png="$ROOT/production/thumbnails/png/$base.png"; broll="$ROOT/production/broll/original/$base.mp4"; out="$ROOT/production/outputs/$base.mp4"
  python "$ROOT/production/automation/synthesize_narration.py" --script "$script" --output "$wav" --voice "${KOKORO_VOICE:-af_heart}" --speed "${KOKORO_SPEED:-0.98}"
  "$ROOT/production/automation/render_video.sh" "$wav" "$music" "$png" "$broll" "$out"
done
python "$ROOT/production/automation/validate_rendered_batch.py" --count "$COUNT"
