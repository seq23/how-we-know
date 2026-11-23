#!/usr/bin/env python3
"""WHISPER ALMANAC SHORTS: one Short a day, cut from the long videos.

    .venv/bin/python loop/whisper_shorts.py run      # on the Mac, in the nightly batch
    .venv/bin/python loop/whisper_shorts.py plan     # the queue and the calendar (no network)

Her rulings: "Shorts from each" (9 Nov 2026) and Shorts go out DAILY (16 Nov
2026). Runs in the batch right after loop/whisper_upload.py
(bin/batch-session.sh phase_whisper_upload). Config `shorts` in
config/whisper_almanac.json.

  * CUT: every uploaded episode whose render is on the Mac is cut into
    `per_video` Shorts, each a DISTINCT moment (the chapter starts first, then
    evenly spaced points; never two within MIN_GAP_S), each ending on a pause,
    at most SHORT_MAX_S, centre-cropped full-bleed to 1080x1920 from the
    picture that already passed the final frame check. No words on screen
    (the brand forbids burned-in captions). 5 long videos a week x 3 = 15
    Shorts for 7 days. whisper_upload.prune_confirmed keeps a render until it
    is cut (MAX_TRIES nights at most). A master put back at an episode's
    render path after its prune (a Studio download) is cut too, then removed.
  * THE QUEUE: the cut files wait on the Mac (renders/whisper/<slug>/shorts/,
    recorded in the kit's `shorts`), oldest first.
  * THE CALENDAR: each Short goes up private with its own publish date,
    `per_day` a day at `publish_time_ct`, the next day that has none and
    never before the day after its parent video goes public; altered
    content = yes, made for kids = no, the AI-voice line first and a link to
    the full video.
  * THE SUPPLY GATE: nothing is dated more than `max_days_ahead` days out
    (WHISPER_SHORTS_HOLD, green); the cut files wait.
  * QUOTA: 1,601 units a Short. On the Almanac's own Google Cloud project
    (whisper-almanac-uploads, 16 Nov 2026) from its own 10,000-unit day;
    before its token moves there, only above How We Know's
    loop/quota.deferrable_reserve(). Short of that it is UPLOAD_QUOTA and the
    next night goes on.
  * OUTPUT line every run (scheduled, queued, dated through). An empty queue is
    NAMED STOP WHISPER_SHORTS_QUEUE_EMPTY (a day may go without a Short); a
    cut or upload that fails is WHISPER_SHORT_FAILED (red).
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import subprocess
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "visuals"))

import whisper_lane as WL                                   # noqa: E402
import whisper_upload as WU                                 # noqa: E402

LANE = "whisper-shorts"
UNITS = 1600 + 1                   # insert + status read
SHORT_MAX_S = 58.0
SHORT_MIN_S = 35.0
MIN_GAP_S = 120.0                  # two Shorts of one video never share a moment
MAX_TRIES = 3                      # nights a render waits to be cut, then it may be pruned
DEFAULTS = {"per_video": 3, "per_day": 1, "publish_time_ct": "19:00", "max_days_ahead": 14,
            "max_per_run": 3, "min_lead_hours": 2}


def scfg(c: dict | None = None) -> dict:
    return {**DEFAULTS, **((c or WL.cfg()).get("shorts") or {})}


def needs_cut(k: dict) -> bool:
    """An uploaded episode not yet cut into its Shorts (or cut and failed under MAX_TRIES)."""
    return bool(k.get("video_id") and not k.get("shorts_cut")
                and int(k.get("short_tries") or 0) < MAX_TRIES)


pending = needs_cut                # whisper_upload.prune_confirmed asks this


def shorts_dir(slug: str) -> Path:
    return WL.video_path(slug).parent / "shorts"


# ------------------------------------------------------------------ the moments
def chapters(k: dict) -> list[tuple[float, str]]:
    """(seconds, title) from the kit description's Chapters block."""
    out = []
    for ln in (k.get("description") or "").splitlines():
        m = re.match(r"^(?:(\d+):)?(\d{1,2}):(\d\d)\s+(.+)$", ln.strip())
        if m:
            h, mi, s, t = m.groups()
            out.append((int(h or 0) * 3600 + int(mi) * 60 + int(s), t.strip()))
    return out


def moments(k: dict, length_s: float, n: int) -> list[tuple[float, str | None]]:
    """n distinct start points: the chapter starts first, then evenly spaced."""
    last = length_s - SHORT_MAX_S - 2
    picks: list[tuple[float, str | None]] = []

    def free(t: float) -> bool:
        return 1.0 <= t <= last and all(abs(t - p) >= MIN_GAP_S for p, _ in picks)

    for t, title in chapters(k):
        # the 0:00 chapter is the welcome, whose words promise the FULL
        # length: a Short starting there takes no name from it
        label = title if t > 0 else None
        t = max(1.0, t + 1.0)
        if len(picks) < n and free(t):
            picks.append((t, label))
    for f in (0.2, 0.5, 0.8, 0.35, 0.65, 0.1, 0.9):
        t = round(length_s * f, 1)
        if len(picks) < n and free(t):
            picks.append((t, None))
    return sorted(picks)


def _pause_end(video: Path, start: float) -> float:
    """Seconds of Short: end on the last pause between SHORT_MIN_S and SHORT_MAX_S."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-ss", f"{start}", "-t", f"{SHORT_MAX_S}",
                        "-i", str(video), "-vn", "-af", "silencedetect=noise=-45dB:d=0.6",
                        "-f", "null", "-"], capture_output=True, text=True)
    ends = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ok = [t for t in ends if SHORT_MIN_S <= t <= SHORT_MAX_S]
    return round(max(ok) + 0.4, 2) if ok else SHORT_MAX_S


def cut_one(src: Path, start: float, out: Path) -> Path:
    """One vertical Short from `start`. Raises on any failure."""
    import shorts as S                                      # noqa: PLC0415
    dur = _pause_end(src, start)
    fo = max(0.0, dur - 1.2)
    vf = ("crop=ih*9/16:ih,scale=1080:1920:flags=lanczos,setsar=1,"
          f"fade=t=in:st=0:d=0.6,fade=t=out:st={fo:.2f}:d=1.2")
    af = f"afade=t=in:st=0:d=0.6,afade=t=out:st={fo:.2f}:d=1.2"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".part.mp4")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{start}",
                    "-i", str(src), "-t", f"{dur}", "-vf", vf, "-af", af,
                    "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(tmp)], check=True)
    got = S.probe_stream(str(tmp))
    secs = S.probe_duration(str(tmp))
    if (got.get("width"), got.get("height")) != (1080, 1920) or not (SHORT_MIN_S - 1 <= secs <= 60):
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"the cut reads {got.get('width')}x{got.get('height')}, {secs:.1f}s; "
                           f"want 1080x1920, {SHORT_MIN_S:.0f}-60s")
    tmp.replace(out)
    return out


def cut(slug: str, k: dict, n: int) -> list[dict]:
    """Cut the episode into n Shorts; the queue rows for its kit."""
    import shorts as S                                      # noqa: PLC0415
    src = WL.video_path(slug)
    if not src.exists():
        raise FileNotFoundError(f"no render at {src}")
    rows = []
    for i, (t, label) in enumerate(moments(k, S.probe_duration(str(src)), n)):
        f = cut_one(src, t, shorts_dir(slug) / f"{slug}-s{i + 1}.mp4")
        rows.append({"n": i + 1, "at_s": t, "label": label, "file": f.name, "video_id": None})
    if not rows:
        raise RuntimeError("the render is too short for a Short")
    return rows


# ------------------------------------------------------------------ the calendar
def body(k: dict, row: dict, c: dict) -> dict:
    """The Short's videos.insert body, from the episode's own kit. One title a
    person would write (the episode's name, then the moment the Short is cut
    from), cut only at a word, no length (a Short is under a minute) and no
    visible #shorts (YouTube files a vertical video under a minute as a Short
    by itself; the tag stays). The AI-voice line opens the description once."""
    name = WL.clip_words(k["title"].split(" · ")[0].split(" (")[0], 70)
    label = WL.clip_words(row.get("label") or "", 99 - len(name) - 2)
    first = label.split(" ")[0] if label else ""
    if label and first != "I" and not first.startswith("I'"):      # "I am..." keeps its capital
        label = label[:1].lower() + label[1:]
    title = f"{name}: {label}" if label else f"{name}, part {row['n']}"
    full = WL.length_label(float(k.get("length_s") or 0))
    ai = c["channel"]["ai_voice_line"]
    rest = "\n".join(ln for ln in (k.get("description") or "").splitlines() if not ln.startswith(ai))
    desc = f"{ai}\nThe full {full} video: https://youtu.be/{k['video_id']}\n\n{rest.strip()}\n"[:4900]
    b = json.loads(json.dumps(k["body"]))
    b["snippet"].update({"title": title, "description": desc})
    b["snippet"]["tags"] = list(dict.fromkeys((b["snippet"].get("tags") or []) + ["shorts"]))
    b["status"] = {"privacyStatus": "private", "containsSyntheticMedia": True,
                   "selfDeclaredMadeForKids": False}
    return b


def dated(ks: dict) -> list[_dt.datetime]:
    return [WU._utc(r["publish_at"]) for k in ks.values() for r in (k.get("shorts") or [])
            if r.get("publish_at")]


def next_slot(ks: dict, now: _dt.datetime, s: dict, parent_at: _dt.datetime | None = None) -> _dt.datetime:
    """The first day from now (with the lead) holding fewer than per_day
    Shorts, and never before the day AFTER its parent video goes public
    (16 Nov 2026: three Shorts were dated Mon-Wed for a Thursday video, so
    their "full video" link pointed at a private video)."""
    hh, mm = (int(x) for x in s["publish_time_ct"].split(":"))
    taken: dict[_dt.date, int] = {}
    for t in dated(ks):
        d = t.astimezone(WU.CT).date()
        taken[d] = taken.get(d, 0) + 1
    earliest = now + _dt.timedelta(hours=s["min_lead_hours"])
    day = earliest.astimezone(WU.CT).date()
    if parent_at:
        day = max(day, parent_at.astimezone(WU.CT).date() + _dt.timedelta(days=1))
    for _ in range(400):
        slot = _dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=WU.CT)
        if slot >= earliest and taken.get(day, 0) < s["per_day"]:
            return slot.astimezone(_dt.timezone.utc)
        day += _dt.timedelta(days=1)
    raise RuntimeError("no free Shorts day in 400 days")


def queue(ks: dict) -> list[tuple[str, dict]]:
    """Cut, not yet uploaded, file on disk; oldest episode first."""
    rows = [(k.get("uploaded_at") or "", s, r) for s, k in ks.items() for r in (k.get("shorts") or [])
            if not r.get("video_id") and (shorts_dir(s) / r["file"]).exists()]
    return [(s, r) for _, s, r in sorted(rows, key=lambda x: (x[0], x[1], x[2]["n"]))]


def afford() -> bool:
    import quota                                            # noqa: PLC0415
    return WU.afford_units(UNITS, quota.deferrable_reserve)


def spend(units: int) -> None:
    WU.book(units, LANE)


def _through(ks: dict) -> str:
    ds = dated(ks)
    return max(ds).astimezone(WU.CT).strftime("%a %d %b") if ds else "nothing dated"


def run(now: _dt.datetime | None = None, yt=None, cutter=None) -> int:
    import breaker                                          # noqa: PLC0415
    import common as C                                      # noqa: PLC0415
    breaker.guard(LANE)
    c = WL.cfg()
    s = scfg(c)
    now = now or _dt.datetime.now(_dt.timezone.utc)
    cutter = cutter or cut
    made, failed, hold = 0, [], ""
    with C.Stage(LANE, zero_work_hint="no Whisper Almanac Short was cut or scheduled") as st:
        ks = WU.kits()
        for slug, k in ks.items():                          # 1. cut every uploaded render
            if not (needs_cut(k) and WL.video_path(slug).exists()):
                continue
            k["short_tries"] = int(k.get("short_tries") or 0) + 1
            WU.write_kit(slug, k)
            try:
                rows = cutter(slug, k, s["per_video"])
            except Exception as e:                          # noqa: BLE001
                failed.append(f"{slug} cut (try {k['short_tries']} of {MAX_TRIES}): {str(e)[:240]}")
                st.note(f"{slug}: not cut tonight: {str(e)[:240]}")
                continue
            k.update({"shorts": rows, "shorts_cut": WU.stamp(now)})
            WU.write_kit(slug, k)
            mins = ", ".join(f"{r['at_s'] / 60:.0f} min" for r in rows)
            st.work(f"cut {len(rows)} Shorts from {slug} at {mins}")
            if k.get("pruned"):                             # a master put back for cutting only
                WL.video_path(slug).unlink(missing_ok=True)
        ks = WU.kits()
        todo = queue(ks)
        if not todo and not failed:
            print(f"OUTPUT 0 Whisper Almanac Short(s) scheduled, 0 queued, dated through {_through(ks)}")
            st.named_stop("WHISPER_SHORTS_QUEUE_EMPTY",
                          f"no cut Whisper Almanac Short is waiting; Shorts are dated through {_through(ks)}",
                          detail={"through": _through(ks)},
                          unblock="Nothing to do: each uploaded long video is cut into "
                                  f"{s['per_video']} Shorts the same night.")
        if todo and yt is None:
            creds = WU.credentials(c)
            if creds is None:
                st.named_stop("WHISPER_YT_TOKEN_INVALID", "no usable @whisperalmanac token",
                              unblock=WU.REAUTH)
            yt = WU.YouTube(creds)
        for slug, row in todo[:s["max_per_run"]]:           # 2. date them, one a day
            k = ks[slug]
            slot = next_slot(ks, now, s, WU._utc(k.get("scheduled_publish_at")))
            if slot > now + _dt.timedelta(days=s["max_days_ahead"]):
                hold = (f"Shorts are dated through {_through(ks)}, the {s['max_days_ahead']}-day "
                        f"limit; {len(todo) - made} wait on the Mac")
                break
            if not afford():
                hold = hold or f"no quota above How We Know's reserve tonight. {WU.quota_line()}"
                break
            f = shorts_dir(slug) / row["file"]
            b = body(k, row, c)
            when = WU.stamp(slot)
            b["status"]["publishAt"] = when
            try:
                vid = yt.insert(b, f)
            except Exception as e:                          # noqa: BLE001
                failed.append(f"{slug} Short {row['n']}: {str(e)[:240]}")
                st.note(f"{slug} Short {row['n']} did not upload: {str(e)[:240]}")
                break
            spend(UNITS)
            row.update({"video_id": vid, "publish_at": when, "title": b["snippet"]["title"],
                        "uploaded_at": WU.stamp(now)})
            WU.write_kit(slug, k)
            f.unlink(missing_ok=True)
            made += 1
            st.work(f"Short {row['n']} of {slug} -> {vid} (private, public "
                    f"{slot.astimezone(WU.CT).strftime('%a %d %b %H:%M CT')})")
        ks = WU.kits()
        left = len(queue(ks))
        print(f"OUTPUT {made} Whisper Almanac Short(s) scheduled, {left} queued, "
              f"dated through {_through(ks)}")
        if failed:
            st.named_stop("WHISPER_SHORT_FAILED",
                          f"{len(failed)} Short step(s) failed: {'; '.join(failed)}"
                          + (f". {made} scheduled this run" if made else ""),
                          detail={"failed": failed}, held_items=[f.split(" ")[0] for f in failed],
                          unblock="Read the reason; the render and the cut files are kept and the "
                                  "next night tries again.")
        if not made and hold.startswith("no quota"):
            st.named_stop("UPLOAD_QUOTA", hold,
                          unblock="Nothing to do: the queue waits and the next night dates it.")
        if not made and hold:
            st.named_stop("WHISPER_SHORTS_HOLD", hold,
                          unblock="Nothing to do: the gate opens as the dated Shorts go public.")
    return 0


def plan() -> int:
    ks = WU.kits()
    now = _dt.datetime.now(_dt.timezone.utc)
    for slug, row in queue(ks):
        print(f"queued {slug} Short {row['n']} at {row['at_s'] / 60:.1f} min ({row.get('label') or 'part'})")
    print(f"next free day {next_slot(ks, now, scfg()).astimezone(WU.CT):%a %d %b %H:%M CT}; "
          f"dated through {_through(ks)}")
    print(f"OUTPUT {len(queue(ks))} Whisper Almanac Short(s) queued")
    return 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["run"]:
        return run()
    if argv[:1] == ["plan"]:
        return plan()
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
