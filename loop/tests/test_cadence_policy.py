"""Cadence, publish order, runway and the retention checkpoint - proven negatively.

Every guard here protects against a failure that LOOKS LIKE SUCCESS, so each one
is proven by breaking the state and showing the failure returns, then restoring:

  * remove `research/publish_order.json`  -> named stop, never filename order
  * back-date it past the threshold       -> stale stop fires
  * drop inventory below the threshold    -> runway warning fires
  * a scoring pass that ranks nothing     -> hard failure, not a green tick
  * viewers leaving in the first 2 min    -> FORMAT PROBLEM finding
  * ask the 4/week scale for a thin queue -> refused, in words, not silently
  * hand the allocator a fatter cadence   -> every existing date is untouched

Hard-fails if it examines zero cases.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import cadence  # noqa: E402
import measure  # noqa: E402
from common import config  # noqa: E402

ORDER = cadence.PUBLISH_ORDER


def check() -> list[str]:
    fails, examined = [], 0
    cfg = config()

    # ------------------------------------------------ cadence is configuration
    examined += 1
    c = cfg["cadence"]
    if c["videos_per_week"] != 2:
        fails.append(f"default cadence is {c['videos_per_week']}, owner set 2")
    if c["escalated"] != 3:
        fails.append(f"escalated cadence is {c['escalated']}, owner set 3")
    if int(c.get("scale", {}).get("to", 0)) != 4:
        fails.append(f"scale target is {c.get('scale', {}).get('to')}, owner "
                     f"set 4 on 2026-09-02")
    for k in ("videos_per_week", "escalated"):
        if c[k] > c["ceiling"]:
            fails.append("cadence exceeds the taxonomy ceiling")
    if int(c["scale"]["to"]) > c["ceiling"]:
        fails.append("the scale target exceeds the taxonomy ceiling")

    # The Shorts half of the same decision. It must not be quietly left behind:
    # Shorts are the only cheap lever on the subscriber half of the threshold,
    # which is the binding one - roughly 12x more binding than watch hours.
    examined += 1
    if not 8 <= int(c.get("shorts_per_week", 0)) <= 10:
        fails.append(f"Shorts cadence is {c.get('shorts_per_week')}/week, "
                     f"outside the owner's 8-10 band")
    if cadence.shorts_effective() < int(c.get("shorts_floor", 4)):
        fails.append("shorts_effective() resolved below its own floor")

    examined += 1
    for f in ("rank.py", "draft.py"):
        src = (LOOP / f).read_text()
        if 'cadence["videos_per_week"]' in src or "per_week = 2" in src:
            fails.append(f"loop/{f} reads cadence directly instead of through "
                         f"loop/cadence.effective()")

    # ------------------------------------------------ escalation is evidence-gated
    ev_file = LOOP / "state" / "authoring_evidence.json"
    backup_ev = ev_file.read_text() if ev_file.exists() else None
    try:
        if ev_file.exists():
            ev_file.unlink()
        examined += 1
        n, why = cadence.effective(explain=True)
        if n != 2:
            fails.append(f"with no authoring evidence the cadence is {n}, "
                         f"expected 2")

        # A validated generated script unlocks 3 - automatically. It unlocks 4
        # too, but only if the queue can carry it, so the assertion is "at
        # least 3, and it said why": pinning it to exactly 3 would make this
        # test fail on the day the scale correctly fires.
        examined += 1
        cadence.record_authoring_evidence(
            "test-generated-script", "loop/drafts/test.md",
            [{"validator": "V8 source-urls", "status": "PASS"}])
        n2, why2 = cadence.effective(explain=True)
        if n2 < 3:
            fails.append(f"a validated generated script did not escalate the "
                         f"cadence: got {n2}, expected at least 3 ({why2})")
        if n2 > int(cfg["cadence"]["ceiling"]):
            fails.append(f"the cadence escalated past the ceiling: {n2}")
        if "escalated" not in why2 and "scaled" not in why2:
            fails.append("the escalation did not explain itself")

        # And with the evidence in hand, the 4/week scale must have made a
        # decision either way and SAID SO - a silent hold at 3 is the failure.
        examined += 1
        want = int(cfg["cadence"]["scale"]["to"])
        ok4, _ = cadence.queue_supports(want)
        if ok4 and n2 != want:
            fails.append(f"the queue supports {want}/week but the cadence "
                         f"resolved to {n2} ({why2})")
        if not ok4 and f"NOT scaled to {want}" not in why2:
            fails.append(f"the scale was withheld without saying so: {why2!r}")
    finally:
        if backup_ev is not None:
            ev_file.write_text(backup_ev)
        elif ev_file.exists():
            ev_file.unlink()

    # Escalation must never be reachable from a backlog, only from evidence.
    examined += 1
    csrc = (LOOP / "cadence.py").read_text()
    if "backlog" in csrc.split("def effective")[1].split("def ")[0].lower():
        fails.append("cadence.effective() considers the backlog; escalation is "
                     "evidence-gated only")

    # ------------------------------------------------ NEGATIVE: order missing
    backup = tempfile.mktemp()
    had_order = ORDER.exists()
    if had_order:
        shutil.copy(ORDER, backup)
    try:
        if had_order:
            ORDER.unlink()
        examined += 1
        try:
            cadence.publish_order()
            fails.append("a MISSING publish_order.json did not raise - the loop "
                         "would fall back to filename order, the exact failure "
                         "this policy exists to prevent")
        except cadence.PublishOrderMissing as e:
            if "filename order" not in str(e) and "episode" not in str(e):
                fails.append("the missing-order stop does not explain why a "
                             "fallback is forbidden")

        # ------------------------------------------- NEGATIVE: order stale
        if had_order:
            raw = json.loads(Path(backup).read_text())
            limit = float(cfg["publish_order"]["staleness_days"])
            old = (dt.datetime.now(dt.timezone.utc)
                   - dt.timedelta(days=limit + 5)).isoformat()
            raw["generated_at"] = old
            ORDER.write_text(json.dumps(raw))
            examined += 1
            try:
                cadence.publish_order()
                fails.append(f"a ranking {limit + 5:.0f} days old did not raise "
                             f"- a stale order publishes on last month's "
                             f"evidence while looking perfectly healthy")
            except cadence.PublishOrderStale:
                pass
            except cadence.PublishOrderMissing:
                fails.append("a stale ranking raised Missing, not Stale")

            # ---------------------------------------- fresh again: no raise
            raw["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
            ORDER.write_text(json.dumps(raw))
            examined += 1
            try:
                order = cadence.publish_order()
                if not order:
                    fails.append("a fresh ranking produced no order")
            except Exception as e:
                fails.append(f"a fresh ranking still raised: {e}")

            # ---------------------------------------- pin is never re-sorted
            # Schema v1.1.0 puts the owner's pinned head at the FRONT of
            # `queue` already, so the pin is honoured by not re-sorting the
            # queue at all. Prove that: reverse the queue and confirm the
            # order follows the file rather than any internal preference.
            examined += 1
            qkey = next((k for k in ("queue", "order", "ranked")
                         if isinstance(raw.get(k), list) and raw[k]), None)
            if qkey:
                first = cadence._slug_of(raw[qkey][0])
                last = cadence._slug_of(raw[qkey][-1])
                flipped = dict(raw)
                flipped[qkey] = list(reversed(raw[qkey]))
                ORDER.write_text(json.dumps(flipped))
                got = cadence.publish_order()
                if got[0] != last:
                    fails.append(f"the loop did not follow the file's own "
                                 f"order: expected {last!r} first, got "
                                 f"{got[0]!r} - something is re-sorting the "
                                 f"queue, which would destroy the pinned head")
                ORDER.write_text(json.dumps(raw))
                if cadence.publish_order()[0] != first:
                    fails.append("restoring the file did not restore the order")

            # ------------------- a gate-killed PIN must survive in the queue
            examined += 1
            _, meta = cadence.ordered_inventory()
            queued = {r["slug"] for r in cadence.ordered_inventory()[0]}
            killed = cadence.killed_slugs()
            for slug in meta.get("queued_despite_kill", []):
                if slug not in queued:
                    fails.append(f"{slug} is pinned with gate_overridden but "
                                 f"was dropped from the queue - filtering the "
                                 f"queue against `killed` destroys the pinned "
                                 f"head")
            if killed and not (killed - queued):
                fails.append("every killed topic is still queued; the gate is "
                             "not excluding anything")

    finally:
        if had_order:
            shutil.copy(backup, ORDER)
            os.unlink(backup)

    # ------------------------------------------------ NEGATIVE: runway warning
    examined += 1
    warn = float(cfg["runway"]["warn_weeks"])
    crit = float(cfg["runway"]["critical_weeks"])
    ok = cadence.runway(2)
    if ok["level"] != "ok":
        fails.append(f"full inventory reported runway level {ok['level']!r}")

    # Force the threshold by asking at an absurd cadence: same arithmetic.
    #
    # The numerator is publishable PLUS videos already uploaded and dated but
    # not yet aired - a scheduled video has not been consumed, it just has not
    # played. This test used to divide unpublished scripts alone, which stopped
    # matching once runway() started counting the scheduled tail on 2026-09-01.
    examined += 1
    inv = ok["publishable"] + ok.get("scheduled_not_yet_aired", 0)
    if inv:
        per = max(1, int(inv / max(0.5, warn - 1)))
        low = cadence.runway(per)
        if low["level"] == "ok":
            fails.append(f"{inv} scripts at {per}/week is "
                         f"{low['weeks_remaining']} weeks and still reported ok "
                         f"against a {warn}-week threshold")
        if "RUNWAY" not in low["message"]:
            fails.append("the runway warning does not announce itself")

    examined += 1
    verylow = cadence.runway(max(1, inv))          # ~1 week left
    if verylow["level"] != "critical":
        fails.append(f"one week of inventory reported {verylow['level']!r}, "
                     f"expected critical")

    # The runway guard must NEVER halt publishing - that is going dark.
    examined += 1
    rank_src = (LOOP / "rank.py").read_text()
    if "breaker.trip" in rank_src:
        fails.append("loop/rank.py trips the breaker; halting publishing to "
                     "protect the backlog IS going dark")

    # ------------------------------------------------ scoring cannot be inert
    examined += 1
    ssrc = (LOOP / "score.py").read_text()
    for code in ("NO_SCORED_CANDIDATES", "NO_RANKING_PRODUCED",
                 "SCORER_QUOTA", "RANKING_STALE_AFTER_SCORING"):
        if code not in ssrc:
            fails.append(f"loop/score.py has no named stop for {code}")
    if "publish_order.json" in ssrc.split("def main")[1] and \
            "write_json" in ssrc.split("def main")[1]:
        fails.append("loop/score.py appears to write the ranking; it is "
                     "read-only there")

    # ------------------------------------------------ retention checkpoint
    examined += 1
    bad = [{"video_id": f"v{i}", "average_view_duration_s": 100} for i in range(4)]
    cp = measure.retention_checkpoint(bad, cfg)
    if cp["format_verdict"] != "FORMAT PROBLEM":
        fails.append("viewers leaving at 1m40s of a 7.5 minute video was not "
                     "reported as a format problem")
    if cp["mean_pct_of_runtime"] > 30:
        fails.append("the checkpoint miscomputed percentage of runtime")

    examined += 1
    good = [{"video_id": f"v{i}", "average_view_duration_s": 260} for i in range(4)]
    if measure.retention_checkpoint(good, cfg)["format_verdict"] != "acceptable":
        fails.append("healthy retention was reported as a format problem")

    examined += 1
    if measure.retention_checkpoint([], cfg)["status"] != "no_data":
        fails.append("no data was not reported as no data")

    # It must reach a human, not sit in JSON.
    examined += 1
    msrc = (LOOP / "measure.py").read_text()
    if "FORMAT_PROBLEM" not in msrc or "named_stop" not in msrc:
        fails.append("a format problem does not raise a named stop, so nobody "
                     "would see it")
    if "retention_finding.md" not in msrc:
        fails.append("no prose finding is written")

    # ------------------------------------------------ locked uploads
    examined += 1
    psrc = (LOOP / "publish.py").read_text()
    if "UPLOADS_LOCKED_PRIVATE" not in psrc:
        fails.append("loop/publish.py has no named stop for a locked upload")
    if "read_status" not in psrc:
        fails.append("loop/publish.py does not verify the video is actually "
                     "public after the flip - an unaudited project accepts the "
                     "request and leaves it private")
    if "hand_published" not in psrc:
        fails.append("loop/publish.py cannot handle videos already published by "
                     "hand; it would try to re-upload them")

    # ---------------------------------- NEGATIVE: the queue-depth guard
    # THE GUARD THAT MAKES SCALING REVERSIBLE. Ask it for a cadence nothing
    # could sustain and it must refuse, in words. Ask it for one the queue
    # plainly carries and it must agree - a guard that refuses everything is
    # as useless as one that refuses nothing.
    examined += 1
    ok, why = cadence.queue_supports(10_000)
    if ok:
        fails.append("queue_supports() approved 10,000 videos a week; the "
                     "queue-depth guard bounds nothing")
    if "floor" not in why and "ZERO" not in why:
        fails.append(f"the queue-depth refusal does not explain itself: {why!r}")

    examined += 1
    depth = (cadence.runway(2)["publishable"]
             + cadence.runway(2).get("scheduled_not_yet_aired", 0))
    if depth:
        # One video a week against the whole queue is unmistakably sustainable.
        ok_low, why_low = cadence.queue_supports(1)
        if not ok_low:
            fails.append(f"queue_supports(1) refused a {depth}-episode queue: "
                         f"{why_low}")
    else:
        fails.append("the queue holds zero episodes, so the positive half of "
                     "the queue-depth proof examined nothing")

    # The refusal must reach a human, not sit in a return value.
    examined += 1
    rsrc = (LOOP / "rank.py").read_text()
    if "CADENCE_SCALE_WITHHELD" not in rsrc:
        fails.append("nothing raises a named stop when the 4/week scale is "
                     "withheld, so the channel would publish at the old rate "
                     "while everyone believed it had scaled")
    if "named_stop" not in rsrc.split("CADENCE_SCALE_WITHHELD")[0][-400:]:
        fails.append("CADENCE_SCALE_WITHHELD is not raised as a named stop")

    # The scale must be evidence-gated, never a bare flag or a date.
    examined += 1
    csrc2 = (LOOP / "cadence.py").read_text()
    eff = csrc2.split("def effective")[1].split("\ndef ")[0]
    if "queue_supports" not in eff or "authoring_evidence" not in eff:
        fails.append("cadence.effective() does not gate the scale on BOTH "
                     "authoring evidence and queue depth")
    for banned in ("2026-10-20", "datetime.date(", "date.today"):
        if banned in eff:
            fails.append(f"cadence.effective() references {banned!r}; the "
                         f"scale must be conditional, not a hardcoded date")

    # ------------------------- NEGATIVE: a fatter cadence moves NOTHING
    # The 14 episodes dated through 2026-10-20 are the thing this whole change
    # must not touch. Re-run the allocator at every cadence up to the ceiling
    # and prove no slot it hands out is one of theirs, and that each one falls
    # after the end of the existing run.
    import sys as _sys
    _sys.path.insert(0, str(LOOP))
    import backfill as _bf                                   # noqa: PLC0415
    import ledger as _led                                    # noqa: PLC0415
    tail = cadence.scheduled_tail()
    if not tail:
        examined += 1
        fails.append("no episode is scheduled ahead, so the 'nothing already "
                     "dated may move' proof examined ZERO rows")
    else:
        taken = {t["scheduled_publish_at"] for t in tail}
        last = tail[-1]["when"]
        led_now = _led.load()
        for pw in range(1, int(cfg["cadence"]["ceiling"]) + 1):
            for when in _bf.schedule_for(led_now, 8, pw):
                examined += 1
                stamp = when.strftime("%Y-%m-%dT%H:%M:%SZ")
                if stamp in taken:
                    fails.append(f"at {pw}/week the allocator re-issued "
                                 f"{stamp}, a slot a scheduled episode already "
                                 f"holds")
                if when <= last:
                    fails.append(f"at {pw}/week the allocator issued {stamp}, "
                                 f"at or before the end of the existing run "
                                 f"({last:%Y-%m-%dT%H:%M:%SZ})")
                if when.astimezone(_bf.PUBLISH_TZ).weekday() in (2, 3):
                    fails.append(f"at {pw}/week a slot landed on a Wednesday "
                                 f"or Thursday, the two measured-weak days")
        # And the ledger itself is untouched by asking.
        examined += 1
        if _led.load()["published"] != led_now["published"]:
            fails.append("re-running the slot allocator MUTATED the ledger")

    # ---------------------------- NEGATIVE: the ladders refuse to wrap
    examined += 1
    try:
        _bf.weekdays_for(int(cfg["cadence"]["ceiling"]) + 1)
        fails.append("the publish weekday ladder wrapped past its evidenced "
                     "days instead of refusing - two episodes would share one "
                     "morning and it would look like a cadence increase")
    except _bf.CadenceExceedsLadder:
        pass
    examined += 1
    if len(set(_bf.weekdays_for(4))) != 4:
        fails.append("the 4/week ladder does not name four distinct days")
    if set(_bf.weekdays_for(2)) != {6, 1}:
        fails.append("the 2/week ladder is no longer Sunday and Tuesday, so "
                     "the fourteen scheduled episodes are on a schedule the "
                     "loop no longer computes")

    import shorts_lane as _sl                                 # noqa: PLC0415
    examined += 1
    try:
        _sl.slot_ladder(len(_sl.SHORTS_SLOT_LADDER) + 1)
        fails.append("the Shorts evening ladder wrapped instead of refusing")
    except _sl.ShortsCadenceExceedsLadder:
        pass
    examined += 1
    rungs = _sl.slot_ladder(cadence.shorts_effective())
    if len(set(rungs)) != len(rungs):
        fails.append("the Shorts ladder stacks two Shorts on one evening slot")
    if any(not 18 <= h <= 21 for _, h in rungs):
        fails.append("a Shorts slot falls outside the 18:00-21:00 evening peak")
    if any(h == _bf.PUBLISH_HOUR_LOCAL for _, h in rungs):
        fails.append("a Shorts slot uses the long-form 10:00 publish hour - a "
                     "Short there lands in the worst part of its own day")

    # ------------------------------- NEGATIVE: the quota reserves hold
    # The arithmetic the higher cadence turns on. A Shorts spend must NOT clear
    # the reserve protecting the day's episode upload, and the peak day at
    # 4 episodes + 2 Shorts + one video's reach must fit inside the allowance.
    import quota as _q                                        # noqa: PLC0415
    examined += 1
    if "shorts" in _q.LONGFORM_LANES or "shorts-cloud" in _q.LONGFORM_LANES:
        fails.append("a Shorts lane counts as a long-form upload in "
                     "quota.LONGFORM_LANES, so publishing a Short would clear "
                     "the reserve held for the day's episode")
    examined += 1
    usable = _q.DAILY - _q.HEADROOM
    peak = 3 * _q.PER_VIDEO + _q.SHORTS_PER_DAY_PEAK * _q.PER_VIDEO \
        + _q.PER_CAPTION + _q.PER_LOCALIZE
    if peak > usable:
        fails.append(f"the peak day at the raised cadence is {peak} units "
                     f"against {usable} usable - the day's last upload would "
                     f"fail with quotaExceeded partway through")
    examined += 1
    if _q.videos_affordable(4, reserve=_q.SHORTS_PER_DAY_PEAK * _q.PER_VIDEO) \
            * _q.PER_VIDEO + _q.SHORTS_PER_DAY_PEAK * _q.PER_VIDEO > usable:
        fails.append("the episode lane can take more than the day allows even "
                     "while reserving the evening's Shorts")

    # ------------------- Shorts exhaustion is a STOP, not a printed line
    # At 4/week the 51 cut Shorts were twelve weeks from running out; at 9/week
    # they are under six. A lane that prints "nothing waiting" and exits 0 is
    # Rule 0's exact defect, and the difference now shows up in weeks.
    examined += 1
    ssrc = (LOOP / "shorts_lane.py").read_text()
    if "SHORTS_INVENTORY_EXHAUSTED" not in ssrc:
        fails.append("loop/shorts_lane.py exits 0 when no Short is waiting; "
                     "an empty Shorts library would look green forever")
    # ...and it must NOT switch format on its own when they run out. The 51
    # already cut are in the current 608px-band format; re-cutting them would
    # discard work already paid for, so native vertical is deferred until they
    # are published and is the owner's call to make, not a mechanism that fires.
    examined += 1
    import re as _re                                        # noqa: PLC0415
    if _re.search(r"\bvertical\w*\s*\(|--vertical\b|vertical=True", ssrc):
        fails.append("loop/shorts_lane.py INVOKES a vertical-format path; the "
                     "move to native vertical is the owner's decision to make "
                     "deliberately, not a mechanism that fires on its own when "
                     "the cut inventory runs out")

    # --------------- the footage harvest never widens the rights gate
    import footage_lane as _fl                              # noqa: PLC0415
    examined += 1
    for rel, gate, _what in _fl.HARVESTERS:
        if not (ROOT / rel).exists():
            continue
        examined += 1
        try:
            _fl.assert_rights_gate(rel, gate)
        except _fl.RightsGateMissing as e:
            fails.append(f"{rel} has lost its provenance gate: {e}")
    # NEGATIVE: a harvester without the gate must be refused.
    examined += 1
    import tempfile as _tf, os as _os                       # noqa: PLC0415
    fd, tmp = _tf.mkstemp(suffix=".py", dir=str(ROOT))
    try:
        with _os.fdopen(fd, "w") as fh:
            fh.write("def harvest():\n    return ['anything at all']\n")
        try:
            _fl.assert_rights_gate(_os.path.basename(tmp), "credit_is_noaa_only")
            fails.append("assert_rights_gate accepted a harvester with no "
                         "NOAA-only allowlist - widening the gate is the "
                         "cheapest way to make a thin pool look healthy and "
                         "the one change this pipeline may not make")
        except _fl.RightsGateMissing:
            pass
    finally:
        _os.unlink(tmp)

    if examined == 0:
        fails.append("examined ZERO cadence-policy cases")
    print(f"inspected {examined} cadence-policy case(s)")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - order never falls back, staleness and runway both fire, "
          "the scale is evidence- and queue-gated, and no cadence moves a slot "
          "already on the calendar" if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
