#!/usr/bin/env bash
# make-captions.sh - caption tracks + measured chapter stamps for every episode.
#
# Derives cue and chapter timings from the REAL narration wavs (the same timing
# authority visuals/assemble.py uses), writes captions/<slug>.{vtt,srt,
# chapters.txt,timing.json}, and corrects the timestamps inside each script's
# own `## Chapters` block so loop/upload.py's build_payload() keeps reading the
# one list it has always read.
#
#   bin/make-captions.sh                  # every fully narrated episode
#   bin/make-captions.sh 05 10            # named episodes
#   bin/make-captions.sh --all-including-estimated
#   bin/make-captions.sh --dry            # do not touch scripts/
#
# Exit 1 means a caption track did not land on its video's ffprobe duration, or
# a script's chapter list could not be reconciled. Exit 2 means nothing was
# selected - a run that did nothing must never exit 0.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

args=()
extra=()
for a in "$@"; do
  case "$a" in
    --dry)                       extra+=(--no-write-script) ;;
    --all-including-estimated)   extra+=(--all --include-estimated) ;;
    *)                           args+=("$a") ;;
  esac
done
if [ ${#args[@]} -eq 0 ] && [[ ! " ${extra[*]-} " =~ --all ]]; then
  extra+=(--all)
fi

command -v ffprobe >/dev/null || { echo "ffprobe not on PATH" >&2; exit 2; }

"$PY" "$ROOT/visuals/captions.py" ${args[@]+"${args[@]}"} ${extra[@]+"${extra[@]}"}
rc=$?

echo
echo "artifacts: $ROOT/captions/"
echo "chapters flow to YouTube via the scripts' own '## Chapters' block,"
echo "which loop/upload.py:build_payload() already parses - no second list."
echo
echo "NOTE: loop/prepare.py freezes loop/work/<slug>.md from scripts/ at stage"
echo "time. Any work copy frozen BEFORE this run carries the old hand-written"
echo "stamps - re-run prepare for those rows."
exit $rc
