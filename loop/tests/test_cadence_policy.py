"""Cadence, publish order, runway and the retention checkpoint - proven negatively.

Every guard here protects against a failure that LOOKS LIKE SUCCESS, so each one
is proven by breaking the state and showing the failure returns, then restoring:

  * remove `research/publish_order.json`  -> named stop, never filename order
  * back-date it past the threshold       -> stale stop fires
  * drop inventory below the threshold    -> runway warning fires
  * a scoring pass that ranks nothing     -> hard failure, not a green tick
  * viewers leaving in the first 2 min    -> FORMAT PROBLEM finding

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
    if c["videos_per_week"] > c["ceiling"] or c["escalated"] > c["ceiling"]:
        fails.append("cadence exceeds the taxonomy ceiling")

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

        # A validated generated script unlocks 3 - automatically.
        examined += 1
        cadence.record_authoring_evidence(
            "test-generated-script", "loop/drafts/test.md",
            [{"validator": "V8 source-urls", "status": "PASS"}])
        n2, why2 = cadence.effective(explain=True)
        if n2 != 3:
            fails.append(f"a validated generated script did not escalate the "
                         f"cadence: got {n2}, expected 3 ({why2})")
        if "escalated" not in why2:
            fails.append("the escalation did not explain itself")
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

    if examined == 0:
        fails.append("examined ZERO cadence-policy cases")
    print(f"inspected {examined} cadence-policy case(s)")
    return fails


if __name__ == "__main__":
    f = check()
    for x in f:
        print(f"  ✗ {x}")
    print("all green - order never falls back, staleness and runway both fire, "
          "escalation is evidence-gated" if not f else f"{len(f)} failure(s)")
    sys.exit(1 if f else 0)
