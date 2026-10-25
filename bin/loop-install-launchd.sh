#!/usr/bin/env bash
# Install (or show) the launchd agents that make the Mac the muscle half.
#
#   DAILY 23:00    bin/batch-session.sh  narrate what has no audio, render what
#                                        has audio, push, then NAMED STOP
#   EVERY 300 s    bin/batch-session.sh --resume-if-interrupted
#                                        resume a night a reboot or a flat
#                                        battery interrupted; a no-op in well
#                                        under a second otherwise (2026-10-12)
#
#   TUE+THU 22:58  bin/food-session.sh   the food lane: footage, voice, render,
#                                        stitch, shelve one food episode a week
#                                        (2026-10-25; it holds the batch's lock)
#
# ONE NARRATOR at a time (the food agent takes the batch's own lock), because
# only one thing here may narrate at once. tuesday and
# thursday are deliberately NOT installed - see the --install block.
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

plist(){ # name script weekday hour [minute]   (weekday "-" = every day)
WD=""
MIN="${5:-0}"
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
        <key>Minute</key><integer>$MIN</integer></dict>
  <key>StandardOutPath</key><string>$LOGDIR/$1.log</string>
  <key>StandardErrorPath</key><string>$LOGDIR/$1.err</string>
  <key>RunAtLoad</key><false/>
</dict></plist>
XML
}

# Every StartInterval seconds rather than on a calendar: the RESUME agent.
# A missed StartCalendarInterval fires on wake from SLEEP, but nothing fires
# after a power-off or a reboot, and a killed batch was never re-run. This one
# asks bin/batch-session.sh --resume-if-interrupted, which owns the decision
# (loop/batch_progress.py gate). RunAtLoad true, so a login after a reboot
# checks at once instead of five minutes later.
plist_interval(){ # name seconds script [args...]
local name="$1" secs="$2"; shift 2
cat <<XML
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.howweknow.$name</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>-lc</string>
    <string>cd $ROOT &amp;&amp; $ROOT/bin/$*</string></array>
  <key>StartInterval</key><integer>$secs</integer>
  <key>StandardOutPath</key><string>$LOGDIR/$name.log</string>
  <key>StandardErrorPath</key><string>$LOGDIR/$name.err</string>
  <key>RunAtLoad</key><true/>
</dict></plist>
XML
}

# Several weekdays at one time: the FOOD agent (2026-10-25). launchd takes an
# ARRAY of calendar dicts for this; one dict per night.
plist_weekdays(){ # name script hour minute weekday...
local name="$1" script="$2" hour="$3" min="$4"; shift 4
local cal=""
for wd in "$@"; do
  cal="$cal
    <dict><key>Weekday</key><integer>$wd</integer>
          <key>Hour</key><integer>$hour</integer>
          <key>Minute</key><integer>$min</integer></dict>"
done
cat <<XML
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.howweknow.$name</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>-lc</string>
    <string>cd $ROOT &amp;&amp; $ROOT/bin/$script</string></array>
  <key>StartCalendarInterval</key>
  <array>$cal
  </array>
  <key>StandardOutPath</key><string>$LOGDIR/$name.log</string>
  <key>StandardErrorPath</key><string>$LOGDIR/$name.err</string>
  <key>RunAtLoad</key><false/>
</dict></plist>
XML
}

AGENT_NAMES="batch nightquit batch-resume food backfill"
print_one(){
  case "$1" in
    batch)        plist batch    batch-session.sh - 23 ;;
    nightquit)    plist nightquit night-quit.sh - 22 55 ;;
    batch-resume) plist_interval batch-resume 300 batch-session.sh --resume-if-interrupted ;;
    # THE FOOD LANE (2026-10-25): Tuesday and Thursday at 22:58, two minutes
    # before the batch, holding the batch's own lock - so it is the ONE
    # narrator on those nights. One food episode a week over two nights; the
    # reason is written at the top of bin/food-session.sh.
    food)         plist_weekdays food food-session.sh 22 58 2 4 ;;
    # DAILY 09:00: the Mac's upload lane (bin/loop-backfill-daily.sh), sharing
    # one ledger with loop-upload-cloud.yml (pull before, push after). It was
    # loaded on this Mac from a hand-written plist the installer did not know;
    # written here since 2026-10-25 so loop/lanes.py has ONE source for it.
    backfill)     plist backfill loop-backfill-daily.sh - 9 ;;
    *) echo "unknown agent: $1 (one of: $AGENT_NAMES)" >&2; return 2 ;;
  esac
}

case "${1:-}" in
  --plist)   # print ONE agent's plist exactly as --install writes it
    print_one "${2:-}"
    ;;
  --install)
    mkdir -p "$AGENTS" "$LOGDIR"
    # ONLY THE BATCH. tuesday and thursday are NOT installed, and that is the
    # whole point of this comment.
    #
    # On 2026-09-05 this script installed all three, and bin/loop-tuesday.sh
    # narrates - it calls bin/run-batch.sh voice. That put a SECOND narrator on
    # the machine, on Tuesdays at 02:00, against a batch that already narrates
    # nightly at 23:00. Narration is the one stage that cannot be parallelised
    # here: the voice model wants roughly four cores, so two of them do not go
    # twice as fast, they go half as fast each. Two narrators also race for the
    # same audio/<slug>/NNNN.wav.
    #
    # docs/OPERATING-MANUAL.md had already recorded that these lanes were
    # deliberately removed on 2026-09-01 and their work moved to the cloud and
    # to the nightly batch. Re-adding them undid a decision the manual had
    # written down. If either is ever wanted again, the question to answer
    # first is which single agent owns narration.
    print_one batch > "$AGENTS/com.howweknow.batch.plist"
    # 22:55, FIVE MINUTES BEFORE THE BATCH: quit the apps that compete with the
    # voice model for RAM (owner decision 2026-10-03; see bin/night-quit.sh).
    print_one nightquit > "$AGENTS/com.howweknow.nightquit.plist"
    # EVERY 300 s: resume a night a reboot or a dead battery interrupted.
    print_one batch-resume > "$AGENTS/com.howweknow.batch-resume.plist"
    # TUE + THU 22:58: the food lane's Mac nights (bin/food-session.sh). It
    # takes the batch's lock, so it is still ONE narrator, never a second.
    print_one food > "$AGENTS/com.howweknow.food.plist"
    print_one backfill > "$AGENTS/com.howweknow.backfill.plist"
    # VERIFY THE XML, never launchctl's own word. A plist launchd cannot parse
    # is still reported "loaded" and simply never fires; that is how two agents
    # sat installed and dead. plutil is the only thing that actually knows.
    for n in $AGENT_NAMES; do
      plutil -lint "$AGENTS/com.howweknow.$n.plist" >/dev/null \
        || { echo "NAMED STOP: com.howweknow.$n.plist is not valid XML; not loading it." >&2; exit 4; }
    done
    for n in $AGENT_NAMES; do
      launchctl unload "$AGENTS/com.howweknow.$n.plist" 2>/dev/null || true
      launchctl load  "$AGENTS/com.howweknow.$n.plist"
      echo "loaded com.howweknow.$n  (logs: $LOGDIR/$n.log)"
    done
    ;;
  --uninstall)
    for n in $AGENT_NAMES tuesday thursday; do
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
    echo "# Daily 23:00 - the batch"; print_one batch
    echo "# Daily 22:55 - quit the apps that compete for RAM"; print_one nightquit
    echo "# Every 300 s - resume an interrupted night"; print_one batch-resume
    echo "# Tue + Thu 22:58 - the food lane"; print_one food
    echo; echo "Nothing was written. Re-run with --install to load these."
    ;;
esac
