#!/usr/bin/env python3
"""WHISPER ALMANAC SHORTS: one vertical Short cut from each uploaded episode.

    .venv/bin/python loop/whisper_shorts.py run     # on the Mac, in the nightly batch
    .venv/bin/python loop/whisper_shorts.py cut SLUG OUT.mp4   # cut only, no network

Her plan (9 Nov 2026: "Shorts from each"). Runs in the batch right after
loop/whisper_upload.py (bin/batch-session.sh phase_whisper_upload), while the
episode's render is still on the Mac: whisper_upload.prune_confirmed keeps a
render until its Short is made or given up (MAX_TRIES nights).

How We Know's cutter (visuals/shorts.py) builds a Short from an episode's beats,
its burned-in caption plate and its direct-answer line; an Almanac master has
none of those, and the Almanac brand forbids burned-in captions. So the cut is
the episode's own opening (the line that says what the video is, a pause-ended
window of at most SHORT_MAX_S), centre-cropped full-bleed to 1080x1920 from the
picture that already passed the final frame check, its probe helpers reused.

  * UPLOADED like the episode: private with the episode's own publish date (so
    the "full video" link works the moment both go public), altered content =
    yes, made for kids = no, the AI-voice line in the first 3 description lines.
  * QUOTA: the shared 10,000-unit day. A Short spends 1,600 and only from what
    is left above loop/quota.deferrable_reserve() (How We Know's episode and
    Shorts slots stay whole); short of that it is UPLOAD_QUOTA, and the next
    night tries again.
  * OUTPUT line every run; a run with no uploaded episode waiting for a Short
    is NAMED STOP WHISPER_SHORTS_NOTHING_TO_CUT (green); a cut or upload that
    fails is WHISPER_SHORT_FAILED (red, with the reason).
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
START_S = 1.0                      # past the opening fade-in
MAX_TRIES = 3                      # nights; then the render may be pruned without one


def pending(k: dict) -> bool:
    """An uploaded episode whose Short is still to be made (or retried)."""
    return bool(k.get("video_id") and not k.get("pruned") and not k.get("short")
                and int(k.get("short_tries") or 0) < MAX_TRIES)


def short_path(slug: str) -> Path:
    return WL.video_path(slug).with_name(f"{slug}-short.mp4")


def _pause_end(video: Path, start: float) -> float:
    """Seconds of Short: end on the last pause between SHORT_MIN_S and SHORT_MAX_S."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-ss", f"{start}", "-t", f"{SHORT_MAX_S}",
                        "-i", str(video), "-vn", "-af", "silencedetect=noise=-45dB:d=0.6",
                        "-f", "null", "-"], capture_output=True, text=True)
    ends = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ok = [t for t in ends if SHORT_MIN_S <= t <= SHORT_MAX_S]
    return round(max(ok) + 0.4, 2) if ok else SHORT_MAX_S


def cut(slug: str, k: dict, out: Path) -> Path:
    """The vertical Short from the finished render. Raises on any failure."""
    import shorts as S                                      # noqa: PLC0415
    src = WL.video_path(slug)
    if not src.exists():
        raise FileNotFoundError(f"no render at {src}")
    dur = min(_pause_end(src, START_S), max(1.0, S.probe_duration(str(src)) - START_S))
    fo = max(0.0, dur - 1.2)
    vf = ("crop=ih*9/16:ih,scale=1080:1920:flags=lanczos,setsar=1,"
          f"fade=t=in:st=0:d=0.6,fade=t=out:st={fo:.2f}:d=1.2")
    af = f"afade=t=in:st=0:d=0.6,afade=t=out:st={fo:.2f}:d=1.2"
    tmp = out.with_suffix(".part.mp4")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{START_S}",
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


def body(k: dict, c: dict) -> dict:
    """The Short's videos.insert body, from the episode's own kit."""
    name = k["title"].split(" · ")[0].strip()
    title = f"{name} · whispered #shorts"[:100]
    full = WL.length_label(float(k.get("length_s") or 0))
    desc = (f"{c['channel']['ai_voice_line']}\n"
            f"The full {full} video: https://youtu.be/{k['video_id']}\n\n{k['description']}")[:4900]
    b = json.loads(json.dumps(k["body"]))
    b["snippet"].update({"title": title, "description": desc})
    b["snippet"]["tags"] = list(dict.fromkeys((b["snippet"].get("tags") or []) + ["shorts"]))
    b["status"] = {"privacyStatus": "private", "containsSyntheticMedia": True,
                   "selfDeclaredMadeForKids": False}
    return b


def publish_at(k: dict, now: _dt.datetime) -> str:
    """The episode's own publish date, or 1 hour from now if that has passed."""
    t = WU._utc(k.get("scheduled_publish_at"))
    soon = now + _dt.timedelta(hours=1)
    return WU.stamp(t if t and t > soon else soon)


def afford() -> bool:
    import quota                                            # noqa: PLC0415
    return quota.units_affordable(UNITS, 1, reserve=quota.deferrable_reserve()) > 0


def spend(units: int) -> None:
    import quota                                            # noqa: PLC0415
    quota.spend(units, LANE)


def run(now: _dt.datetime | None = None, yt=None, cutter=None) -> int:
    import breaker                                          # noqa: PLC0415
    import common as C                                      # noqa: PLC0415
    breaker.guard(LANE)
    c = WL.cfg()
    now = now or _dt.datetime.now(_dt.timezone.utc)
    cutter = cutter or cut
    made = 0
    with C.Stage(LANE, zero_work_hint="no uploaded Whisper Almanac episode is waiting for its Short") as st:
        ks = WU.kits()
        todo = [s for s, k in ks.items() if pending(k) and WL.video_path(s).exists()]
        if not todo:
            print("OUTPUT 0 Whisper Almanac Short(s) cut and scheduled")
            st.named_stop("WHISPER_SHORTS_NOTHING_TO_CUT",
                          "no uploaded Whisper Almanac episode has its render on the Mac and no Short yet",
                          unblock="Nothing to do: the next uploaded episode gets its Short the same night.")
        if yt is None:
            creds = WU.credentials(c)
            if creds is None:
                st.named_stop("WHISPER_YT_TOKEN_INVALID", "no usable @whisperalmanac token",
                              unblock=WU.REAUTH)
            yt = WU.YouTube(creds)
        failed = []
        for slug in todo:
            k = ks[slug]
            if not afford():
                print(f"OUTPUT {made} Whisper Almanac Short(s) cut and scheduled")
                st.named_stop("UPLOAD_QUOTA", f"no quota left today above How We Know's reserve for "
                              f"{slug}'s Short ({UNITS} units). {WU.quota_line()}",
                              unblock="Nothing to do: the render is kept and the next night cuts it.")
            k["short_tries"] = int(k.get("short_tries") or 0) + 1
            WU.write_kit(slug, k)
            out = short_path(slug)
            try:
                cutter(slug, k, out)
                b = body(k, c)
                when = publish_at(k, now)
                b["status"]["publishAt"] = when
                vid = yt.insert(b, out)
            except Exception as e:                          # noqa: BLE001
                failed.append(f"{slug} (try {k['short_tries']} of {MAX_TRIES}): {str(e)[:240]}")
                st.note(f"{slug}: no Short tonight: {str(e)[:240]}")
                continue
            finally:
                out.unlink(missing_ok=True)
            spend(UNITS)
            k["short"] = {"video_id": vid, "scheduled_publish_at": when, "at": WU.stamp(now),
                          "title": b["snippet"]["title"]}
            WU.write_kit(slug, k)
            made += 1
            st.work(f"Short of {slug} -> {vid} (private, public {when}), links https://youtu.be/{k['video_id']}")
        print(f"OUTPUT {made} Whisper Almanac Short(s) cut and scheduled")
        if failed:
            st.named_stop("WHISPER_SHORT_FAILED",
                          f"{len(failed)} Short(s) not made: {'; '.join(failed)}"
                          + (f". {made} made this run" if made else ""),
                          detail={"failed": failed}, held_items=[f.split(" ")[0] for f in failed],
                          unblock="Read the reason; the render is kept and the next night tries again "
                                  f"({MAX_TRIES} nights at most, then the episode goes without a Short).")
    return 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["run"]:
        return run()
    if argv[:1] == ["cut"] and len(argv) == 3:
        k = WU.read_kit(argv[1])
        print(cut(argv[1], k, Path(argv[2])))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
