#!/usr/bin/env python3
"""WHOSE NIGHT IS IT: the Mac's narrator nights, 5 Whisper Almanac to 2 How We Know.

    python loop/night_split.py tonight     # line 1: whisper | hwk; then the notes
    python loop/night_split.py report      # the split, both gates, the re-check date

Her ruling, 6 Nov 2026: the Mac's narration nights split 5 to Whisper Almanac
and 2 to How We Know long-form; How We Know Shorts keep going; re-check at day
30 with real views from both channels (config/whisper_almanac.json `split`).
Context she gave: How We Know Deep has 113 videos, 31 subscribers and mostly
7-21 views a video.

  * How We Know nights are Monday (the food session's night) and Friday (the
    batch's deep sea and materials night); the other five are Almanac nights.
  * The supply gates come FIRST (loop/supply_gate.py; her 12 Oct rule): the
    split applies only to nights the gates allow. A How We Know night whose
    long-form gate HOLDs is given to the Almanac; an Almanac night whose own
    gate holds goes to How We Know.
  * Until her whisper sample exists (or with nothing ready to voice) an
    Almanac night falls back to How We Know, so the Mac never sits idle. That
    is a NOTE, never a red.
  * A night belongs to the evening it starts on: 02:00 on Wednesday is
    Tuesday's night.

The Whisper Almanac's own supply gate is the same rule from day one: made and
not uploaded (rendered or fully voiced) over 14 days of its upload rate.
Before its first upload the rate is the planned one (one sleep episode and one
affirmations script a week).
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parent
sys.path.insert(0, str(LOOP))

import supply_gate as G                                     # noqa: E402

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def split_cfg() -> dict:
    import whisper_lane as WL                               # noqa: PLC0415
    return WL.cfg()["split"]


def night_of(now: _dt.datetime) -> _dt.date:
    return (now - _dt.timedelta(days=1)).date() if now.hour < 12 else now.date()


def planned(now: _dt.datetime, cfg: dict | None = None) -> str:
    cfg = cfg or split_cfg()
    return "hwk" if DAYS[night_of(now).weekday()] in cfg["hwk_nights"] else "whisper"


def whisper_supply(now: _dt.datetime | None = None) -> dict:
    import whisper_lane as WL                               # noqa: PLC0415
    now = now or _dt.datetime.now(_dt.timezone.utc)
    made, times = 0, []
    for f in WL.all_scripts():
        slug = f.stem
        kit = WL.KITS / slug / "kit.json"
        k = json.loads(kit.read_text()) if kit.exists() else {}
        if k.get("uploaded_at"):
            times.append(k["uploaded_at"])
            continue
        done, n = WL.voiced(slug)
        if WL.video_path(slug).exists() or (n and done == n):
            made += 1
    per, n = G.rate(times, now)
    if not n:
        per = float(WL.cfg()["split"]["planned_uploads_per_week"]) / 7
    return G.verdict("whisper", made, per, n, now)


def whisper_ready() -> tuple[bool, str]:
    import whisper_lane as WL                               # noqa: PLC0415
    if WL.find_sample() is None:
        return False, "her whisper sample is not on the Mac yet"
    if not WL.queue():
        return False, "no whisper script is waiting for voice"
    return True, ""


def tonight(now: _dt.datetime | None = None, *, hwk_gate=None, whisper_gate=None,
            ready=None, cfg: dict | None = None) -> tuple[str, list[str]]:
    now = now or _dt.datetime.now()
    plan = planned(now, cfg)
    hg = hwk_gate if hwk_gate is not None else G.check("longform")
    wg = whisper_gate if whisper_gate is not None else whisper_supply()
    ok, why = ready if ready is not None else whisper_ready()
    day = DAYS[night_of(now).weekday()]
    notes = [f"night of {night_of(now):%a %d %b}: a {'How We Know' if plan == 'hwk' else 'Whisper Almanac'} "
             f"night by the 5:2 split", f"How We Know long-form {hg['line']}", f"Whisper Almanac {wg['line']}"]
    if plan == "whisper":
        if ok and not wg["hold"]:
            return "whisper", notes
        notes.append(f"note: this Almanac night falls back to How We Know ({why or wg['line']})")
        return "hwk", notes
    if hg["hold"] and ok and not wg["hold"]:
        notes.append(f"note: How We Know's {day} night is given to the Almanac (its supply gate holds)")
        return "whisper", notes
    return "hwk", notes


def main(argv: list[str]) -> int:
    if argv[:1] == ["tonight"]:
        kind, notes = tonight()
        print(kind)
        for n in notes:
            print(f"  {n}")
        return 0
    if argv[:1] == ["report"]:
        c = split_cfg()
        print(f"split: Almanac {', '.join(d for d in DAYS if d not in c['hwk_nights'])}; "
              f"How We Know {', '.join(c['hwk_nights'])}; re-check {c['recheck_on']}")
        print(G.check("longform")["line"])
        print(whisper_supply()["line"])
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
