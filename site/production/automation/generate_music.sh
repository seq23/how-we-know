#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd); OUT="$ROOT/production/audio/music"; mkdir -p "$OUT"
# Original procedural ambient beds. No sampled recordings.
ffmpeg -hide_banner -loglevel error -y -f lavfi -i "sine=f=55:d=75:r=48000" -f lavfi -i "anoisesrc=color=pink:duration=75:sample_rate=48000:amplitude=.05" -filter_complex "[0:a]volume=.15,lowpass=f=180[a0];[1:a]lowpass=f=900,volume=.12[a1];[a0][a1]amix=2,afade=t=in:d=4,afade=t=out:st=70:d=5" -c:a aac -b:a 128k "$OUT/ambient-01.m4a"
ffmpeg -hide_banner -loglevel error -y -f lavfi -i "sine=f=73.42:d=75:r=48000" -f lavfi -i "sine=f=110:d=75:r=48000" -filter_complex "[0:a]volume=.08,tremolo=f=.08:d=.25[a0];[1:a]volume=.04,tremolo=f=.05:d=.2[a1];[a0][a1]amix=2,afade=t=in:d=4,afade=t=out:st=70:d=5" -c:a aac -b:a 128k "$OUT/ambient-02.m4a"
ffmpeg -hide_banner -loglevel error -y -f lavfi -i "anoisesrc=color=brown:duration=75:sample_rate=48000:amplitude=.08" -filter_complex "lowpass=f=420,highpass=f=35,chorus=.5:.7:40:.2:0.2:2,afade=t=in:d=4,afade=t=out:st=70:d=5" -c:a aac -b:a 128k "$OUT/ambient-03.m4a"
ffmpeg -hide_banner -loglevel error -y -f lavfi -i "sine=f=43.65:d=75:r=48000" -f lavfi -i "anoisesrc=color=blue:duration=75:sample_rate=48000:amplitude=.025" -filter_complex "[0:a]volume=.12,vibrato=f=.06:d=.1[a0];[1:a]lowpass=f=1200,volume=.08[a1];[a0][a1]amix=2,afade=t=in:d=4,afade=t=out:st=70:d=5" -c:a aac -b:a 128k "$OUT/ambient-04.m4a"
