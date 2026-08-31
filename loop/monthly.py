"""Monthly review — read a month of measurement and say what to change.

The weekly `measure.py` writes one row per video per week into
`loop/state/measurement.json`. Nobody reads a JSON file. This stage reads a
month of it and produces two things:

  loop/state/monthly/<YYYY-MM>.json   the numbers, for the next month to compare
  loop/state/monthly/<YYYY-MM>.md     prose the owner actually reads

**Every finding names the evidence and the threshold it crossed.** A review that
says "engagement is soft" is worthless; one that says "average view duration is
2m41s against a 8m06s runtime, 33%, below the 35% floor on 4 of 5 videos" can be
acted on or argued with.

**A month with too little data says so and stops.** Two videos is not a trend,
and a confident recommendation from two data points is worse than silence — it
spends the owner's trust on noise. `MIN_VIDEOS` and `MIN_VIEWS` are the floor,
and falling below them is a NAMED STOP, not a quiet pass.

Rule 0 applies: this exits non-zero rather than reporting a green month it did
not actually measure.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "loop"))

from common import Stage, config, read_json, write_json  # noqa: E402

MEASURE = ROOT / "loop/state/measurement.json"
LEDGER = ROOT / "loop/state/ledger.json"
OUTDIR = ROOT / "loop/state/monthly"

# Below these, a month is not evidence. Chosen deliberately: at 2 videos/week a
# month is ~8 videos, so 3 is a quarter of that and still thin. Any conclusion
# from fewer is a story about noise.
MIN_VIDEOS = 3
MIN_VIEWS = 100


def month_id(d: dt.date | None = None) -> str:
    d = d or dt.date.today()
    return f"{d.year:04d}-{d.month:02d}"


def _in_month(row: dict, mid: str) -> bool:
    at = row.get("at") or ""
    return at[:7] == mid


def collect(mid: str) -> list[dict]:
    m = read_json(MEASURE, default={"videos": []})
    return [r for r in m.get("videos", []) if _in_month(r, mid)]


def review(rows: list[dict], cfg: dict) -> dict:
    """Turn a month of rows into findings, each with its evidence."""
    runtime_min = float(cfg["retention"].get("runtime_minutes", 7.5))
    floor_pct = float(cfg["retention"].get("floor_pct", 35))
    early_min = float(cfg["retention"].get("early_exit_minutes", 2.0))

    measured = [r for r in rows if r.get("average_view_duration_s")]
    views = sum(r.get("views") or 0 for r in rows)
    findings: list[dict] = []

    if len(measured) < MIN_VIDEOS or views < MIN_VIEWS:
        return {
            "sufficient": False,
            "videos_measured": len(measured),
            "views": views,
            "why": (f"{len(measured)} measured video(s) and {views} view(s) is below "
                    f"the floor of {MIN_VIDEOS} videos / {MIN_VIEWS} views. A "
                    f"recommendation from this much data would be a story about "
                    f"noise, so this month makes none."),
            "findings": [],
        }

    avd = sum(r["average_view_duration_s"] for r in measured) / len(measured)
    avp = sum((r.get("average_view_percentage") or 0) for r in measured) / len(measured)
    below = [r for r in measured
             if (r.get("average_view_percentage") or 0) < floor_pct]
    early = [r for r in measured
             if r["average_view_duration_s"] < early_min * 60]

    # 1. THE FORMAT QUESTION. This is the finding that can invalidate the plan.
    if len(early) >= max(2, len(measured) // 2):
        findings.append({
            "id": "FORMAT_TOO_LONG",
            "severity": "high",
            "evidence": (f"{len(early)} of {len(measured)} videos hold viewers under "
                         f"{early_min:.0f} minutes against a {runtime_min:.1f} minute "
                         f"runtime; month average {avd/60:.1f} min ({avp:.0f}%)."),
            "decision": ("Shorten the format, or move the answer earlier. Viewers "
                         "leaving in the first two minutes did not dislike the "
                         "ending - they never reached it."),
        })
    elif below and len(below) >= len(measured) // 2:
        findings.append({
            "id": "RETENTION_BELOW_FLOOR",
            "severity": "medium",
            "evidence": (f"{len(below)} of {len(measured)} videos are under the "
                         f"{floor_pct:.0f}% retention floor; month average {avp:.0f}%."),
            "decision": ("Watch one more month before changing the format. One month "
                         "below floor is a signal, two is a pattern."),
        })
    else:
        findings.append({
            "id": "RETENTION_OK",
            "severity": "info",
            "evidence": (f"month average {avp:.0f}% retention, {avd/60:.1f} min of a "
                         f"{runtime_min:.1f} min runtime; {len(below)} of "
                         f"{len(measured)} below the {floor_pct:.0f}% floor."),
            "decision": "No format change indicated.",
        })

    # 2. WHAT ACTUALLY GOT WATCHED. Ranking picks topics on demand and
    #    competition; this is the only place reality answers back.
    ranked = sorted(measured, key=lambda r: r.get("views") or 0, reverse=True)
    if len(ranked) >= 3:
        top, bottom = ranked[0], ranked[-1]
        spread = (top.get("views") or 0) - (bottom.get("views") or 0)
        findings.append({
            "id": "TOPIC_SPREAD",
            "severity": "info",
            "evidence": (f"best {top['video_id']} at {top.get('views')} views, "
                         f"worst {bottom['video_id']} at {bottom.get('views')}; "
                         f"spread {spread}."),
            "decision": ("Feed this back into scoring only if the spread is large "
                         "and repeats. One month of view counts on a young channel "
                         "is mostly a measure of when each video was published."),
        })

    return {"sufficient": True, "videos_measured": len(measured), "views": views,
            "avg_view_duration_s": round(avd, 1),
            "avg_view_percentage": round(avp, 1), "findings": findings}


def to_prose(mid: str, r: dict) -> str:
    out = [f"# Monthly review — {mid}", ""]
    if not r["sufficient"]:
        out += ["**Not enough data to draw a conclusion.**", "", r["why"], "",
                "This is a named stop, not a pass. Nothing was decided.", ""]
        return "\n".join(out)
    out += [f"{r['videos_measured']} videos measured, {r['views']} views, "
            f"average retention {r['avg_view_percentage']}% "
            f"({r['avg_view_duration_s']/60:.1f} min).", ""]
    for f in r["findings"]:
        out += [f"## {f['id']}  ({f['severity']})", "",
                f"**Evidence.** {f['evidence']}", "",
                f"**Decision.** {f['decision']}", ""]
    return "\n".join(out)


def main() -> int:
    cfg = config()
    mid = month_id()
    with Stage("monthly-review") as st:
        rows = collect(mid)
        st.note(f"{len(rows)} measurement row(s) in {mid}")
        r = review(rows, cfg)
        OUTDIR.mkdir(parents=True, exist_ok=True)
        write_json(OUTDIR / f"{mid}.json", r)
        (OUTDIR / f"{mid}.md").write_text(to_prose(mid, r) + "\n")
        st.work(f"wrote loop/state/monthly/{mid}.md")

        if not r["sufficient"]:
            st.named_stop(
                "MONTH_NOT_MEASURABLE", r["why"],
                detail=r,
                unblock=("Nothing to do if the channel is young - this clears itself "
                         "as videos accumulate. If it persists once several videos "
                         "have been public for weeks, the measurement lane is broken: "
                         "check that the YouTube Analytics API is enabled on the Cloud "
                         "project AND that the token carries yt-analytics.readonly. "
                         "Both are required and a 403 looks identical either way. "
                         "auth/check_auth.py reports the live scopes."))
            return 3

        high = [f for f in r["findings"] if f["severity"] == "high"]
        if high:
            st.named_stop(
                "MONTHLY_FINDING", "; ".join(f["id"] for f in high),
                detail=r,
                unblock=(f"Read loop/state/monthly/{mid}.md. A high finding is a "
                         f"decision for the owner, not something the loop should act "
                         f"on by itself - changing the format is not a thing to "
                         f"automate off one month."))
            return 3
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
