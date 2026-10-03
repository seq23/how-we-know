#!/bin/bash
# night-quit.sh — at 22:55, quit the apps that compete with the voice model for RAM.
#
# WHY. This is an 8 GB M2. On five of seven nights (26 Sep – 2 Oct 2026) the
# chatterbox model took 444–1152 s to load (20–32 s on a quiet night) and the
# batch produced 1–16 beats instead of ~40: the machine was swapping, with
# Chrome alone holding ~1.3 GB. Owner decision 2026-10-03: quit Chrome, Signal
# and Spotify at 22:55 on batch nights. Chrome restores its tabs on reopen.
#
# This is preparation, not work: it never fails the night. It exits 0 whether
# or not anything was running, and says what it did.
set -u
LOG="$HOME/Library/Logs/how-we-know/nightquit.log"
mkdir -p "$(dirname "$LOG")"
free_gb() { vm_stat | awk '/Pages free/{gsub(/\./,"",$3); printf "%.1f", $3*16384/1073741824}'; }
echo "=== night-quit $(date '+%Y-%m-%d %H:%M') free $(free_gb) GB before ===" >> "$LOG"
for app in "Google Chrome" "Signal" "Spotify"; do
  if pgrep -xq "$app" || pgrep -q "$app" 2>/dev/null; then
    if osascript -e "tell application \"$app\" to quit" >/dev/null 2>&1; then
      echo "  quit $app" >> "$LOG"
    else
      echo "  $app did not quit cleanly (left running)" >> "$LOG"
    fi
  else
    echo "  $app not running" >> "$LOG"
  fi
done
sleep 10
echo "  free $(free_gb) GB after" >> "$LOG"
exit 0
