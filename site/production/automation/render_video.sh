#!/usr/bin/env bash
set -euo pipefail
if [[ $# -lt 5 ]]; then echo "usage: $0 NARRATION_WAV MUSIC_M4A THUMBNAIL_PNG BROLL_MP4 OUTPUT_MP4" >&2; exit 2; fi
NARR="$1"; MUSIC="$2"; IMAGE="$3"; BROLL="$4"; OUT="$5"
for f in "$NARR" "$MUSIC" "$IMAGE" "$BROLL"; do [[ -f "$f" ]] || { echo "missing: $f" >&2; exit 3; }; done
mkdir -p "$(dirname "$OUT")"
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$NARR")
ffmpeg -hide_banner -loglevel error -y \
  -stream_loop -1 -i "$BROLL" -i "$NARR" -stream_loop -1 -i "$MUSIC" -loop 1 -i "$IMAGE" \
  -filter_complex "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30,format=yuv420p[bg];[3:v]scale=1920:1080,format=rgba,fade=t=out:st=2.4:d=0.6:alpha=1[cover];[bg][cover]overlay=0:0:enable='lte(t,3)'[v];[1:a]loudnorm=I=-16:LRA=7:TP=-1.5[voice];[2:a]volume=0.075,afade=t=in:st=0:d=2[music];[voice][music]amix=inputs=2:duration=first:dropout_transition=2[a]" \
  -map "[v]" -map "[a]" -t "$DUR" -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 192k -movflags +faststart "$OUT"
printf '{"output":"%s","duration":%s}\n' "$OUT" "$DUR"
