#!/usr/bin/env bash
# Install (or show) the launchd agents that make the Mac the muscle half.
#
#   DAILY 23:00    bin/batch-session.sh  narrate what has no audio, render what
#                                        has audio, push, then NAMED STOP
#   Tuesday 02:00  bin/loop-tuesday.sh   pull, synthesise, render, receipts, push
#   Thursday 02:00 bin/loop-thursday.sh  upload PRIVATE, receipts, push
#
# 23:00 is the owner's choice (2026-09-04): start the night's narration when
# she has stopped using the Mac, so the ~4 cores the voice model takes are not
# competing with her. The job holds the machine awake for its own duration with
# caffeinate -dimsu and releases it when it stops.
#
# WHY THE BATCH AGENT IS DAILY AND WHY THAT IS NOT WASTEFUL. Narration measures
# at ~0.8 beats a minute on this M2, so the 18-episode materials queue is ~27
# hours of voice - it cannot finish inside one night and it will be interrupted.
# bin/batch-session.sh is resumable by construction: every beat already on disk
# is skipped, and an episode is rendered only when its wav count equals its
# plan's beat count. So a nightly agent that runs it is a job that RESUMES each
# night until the queue is empty and then takes its named stop. A run with
# nothing to do prints why and exits 0 in about a second.
#
# NOTHING HERE OPENS AN AGENT OR AN LLM. Narration and rendering are
# deterministic local programs; they need torch and ffmpeg, not a model that
# reasons. The only stage that needs a language model is AUTHORING a new
# script, and that already runs in GitHub Actions on Mondays via loop/draft.py
# and loop/author.py. When the script queue empties, the batch's own named stop
# says so in those words - "the shortfall is SCRIPTS, not audio" - and the
# cloud lane, not this Mac, is what refills it.
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

plist(){ # name script weekday hour   (weekday "-" = every day)
WD=""
[ "$3" != "-" ] && WD="<key>Weekday</key><integer>$3</integer>"
cat <<XML
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.howweknow.$1</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>-lc</string>
    <!-- &amp;&amp; not && : a plist is XML, and a bare ampersand makes the
         whole file invalid. launchctl still reports "loaded", which is why
         this survived unnoticed - an agent that cannot be parsed is an
         agent that never fires, reported as success. -->
    <string>cd $ROOT &amp;&amp; $ROOT/bin/$2</string></array>
  <key>StartCalendarInterval</key>
  <dict>$WD
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
    plist batch    batch-session.sh - 23 > "$AGENTS/com.howweknow.batch.plist"
    plist tuesday  loop-tuesday.sh  2 2 > "$AGENTS/com.howweknow.tuesday.plist"
    plist thursday loop-thursday.sh 4 2 > "$AGENTS/com.howweknow.thursday.plist"
    # VERIFY THE XML, never launchctl's own word. A plist launchd cannot parse
    # is still reported "loaded" and simply never fires; that is how two agents
    # sat installed and dead. plutil is the only thing that actually knows.
    for n in batch tuesday thursday; do
      plutil -lint "$AGENTS/com.howweknow.$n.plist" >/dev/null \
        || { echo "NAMED STOP: com.howweknow.$n.plist is not valid XML; not loading it." >&2; exit 4; }
    done
    for n in batch tuesday thursday; do
      launchctl unload "$AGENTS/com.howweknow.$n.plist" 2>/dev/null || true
      launchctl load  "$AGENTS/com.howweknow.$n.plist"
      echo "loaded com.howweknow.$n  (logs: $LOGDIR/$n.log)"
    done
    ;;
  --uninstall)
    for n in batch tuesday thursday; do
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
    echo "# Daily 23:00"; plist batch batch-session.sh - 23
    echo; echo "# Tuesday 02:00"; plist tuesday loop-tuesday.sh 2 2
    echo; echo "# Thursday 02:00"; plist thursday loop-thursday.sh 4 2
    echo; echo "Nothing was written. Re-run with --install to load these."
    ;;
esac
