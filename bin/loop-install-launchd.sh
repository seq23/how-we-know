#!/usr/bin/env bash
# Install (or show) the two launchd agents that make the Mac the muscle half.
#
#   Tuesday 02:00  bin/loop-tuesday.sh   pull, synthesise, render, receipts, push
#   Thursday 02:00 bin/loop-thursday.sh  upload PRIVATE, receipts, push
#
# launchd rather than cron: a cron job on a sleeping Mac simply does not run,
# whereas launchd fires a missed StartCalendarInterval as soon as the machine
# wakes. Combined with the caffeinate wrapper in bin/run-batch.sh, that is the
# difference between a render that happens and one that silently did not.
#
#   bin/loop-install-launchd.sh            # print the plists and do nothing
#   bin/loop-install-launchd.sh --install  # write them and load them
#   bin/loop-install-launchd.sh --status
#   bin/loop-install-launchd.sh --uninstall
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
LOGDIR="$HOME/Library/Logs/how-we-know"

plist(){ # name script weekday hour
cat <<XML
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.howweknow.$1</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>-lc</string>
    <string>cd $ROOT && $ROOT/bin/$2</string></array>
  <key>StartCalendarInterval</key>
  <dict><key>Weekday</key><integer>$3</integer>
        <key>Hour</key><integer>$4</integer>
        <key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>$LOGDIR/$1.log</string>
  <key>StandardErrorPath</key><string>$LOGDIR/$1.err</string>
  <key>RunAtLoad</key><false/>
</dict></plist>
XML
}

case "${1:-}" in
  --install)
    mkdir -p "$AGENTS" "$LOGDIR"
    plist tuesday  loop-tuesday.sh  2 2 > "$AGENTS/com.howweknow.tuesday.plist"
    plist thursday loop-thursday.sh 4 2 > "$AGENTS/com.howweknow.thursday.plist"
    for n in tuesday thursday; do
      launchctl unload "$AGENTS/com.howweknow.$n.plist" 2>/dev/null || true
      launchctl load  "$AGENTS/com.howweknow.$n.plist"
      echo "loaded com.howweknow.$n  (logs: $LOGDIR/$n.log)"
    done
    ;;
  --uninstall)
    for n in tuesday thursday; do
      launchctl unload "$AGENTS/com.howweknow.$n.plist" 2>/dev/null || true
      rm -f "$AGENTS/com.howweknow.$n.plist"
      echo "removed com.howweknow.$n"
    done
    ;;
  --status)
    launchctl list | grep -i howweknow || echo "no how-we-know agents loaded"
    echo "logs: $LOGDIR"
    ;;
  *)
    echo "# Tuesday 02:00"; plist tuesday loop-tuesday.sh 2 2
    echo; echo "# Thursday 02:00"; plist thursday loop-thursday.sh 4 2
    echo; echo "Nothing was written. Re-run with --install to load these."
    ;;
esac
