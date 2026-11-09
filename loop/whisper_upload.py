#!/usr/bin/env python3
"""THE WHISPER ALMANAC UPLOAD: a finished episode, scheduled on @whisperalmanac.

    .venv/bin/python loop/whisper_upload.py run      # on the Mac, in the nightly batch
    .venv/bin/python loop/whisper_upload.py plan     # what would go up, and when (no network)

Runs on the Mac (bin/batch-session.sh, step `whisper-upload`, after the
whisper step). Whisper masters go from the Mac straight to YouTube and never
sit in R2 (docs/WHISPER_ALMANAC.md, Storage). How We Know's rules, reused:

  * ONLY A CHECKED EPISODE GOES UP: every lane check again here (the script
    rules, loop/whisper_lane.script_problems; the kit rules, meta_problems;
    a measured length), then the final frame check on the finished file
    (visuals/whisper_frame_check.py: one frame every 20 s, OCR, measured
    luma and a free vision model; the sleep gate). A failure is NAMED STOP
    [FRAME_CHECK_FAILED]; the file is
    set aside (never deleted) and the next episode goes on.
  * PRIVATE WITH A PUBLISH DATE, never public at once, as How We Know does
    (loop/backfill.py): 20:00 Central on the format's own days
    (config/whisper_almanac.json `upload`). The publishAt rides in the
    videos.insert body itself, so the altered-content answer
    (status.containsSyntheticMedia = true: the voice is a clone of hers) and
    made-for-kids = no are never reset by a second status write.
  * THE SUPPLY GATE: no new upload of a format while 14+ days of it already
    wait on YouTube (her 12 Oct rule). A HOLD is a note, never a red; the
    render waits on the Mac.
  * YOUTUBE CONFIRMS BEFORE ANYTHING IS DELETED: the upload is recorded only
    once videos.list shows the id with processing started; the local render
    and its voice wavs are deleted on a later run, only once YouTube reports
    it `processed` with no rejection (the disk-guard rule of
    loop/render_prune.prune_uploaded; the R2 half does not apply - masters
    never go to R2).
  * NAMED STOPS someone sees: WHISPER_YT_TOKEN_INVALID, UPLOAD_QUOTA and
    FRAME_CHECK_FAILED (and the other red ones) are written to
    loop/state/stops/ (the Sunday digest reads them; the batch pushes them)
    and one line goes into her morning email's Notices (Boss OS
    addMorningLines).

LOOP_DRY_RUN=1 refuses the credential: nothing is sent to YouTube.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
sys.path.insert(0, str(ROOT / "visuals"))

import whisper_lane as WL                                   # noqa: E402

LANE = "whisper-upload"
CT = ZoneInfo("America/Chicago")
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
API = "https://www.googleapis.com/youtube/v3"
THUMB_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set?uploadType=media&videoId="
UNITS = 1600 + 50 + 1 + 1          # insert + thumbnail + channel read + status read
FAILED = ".frame-check-failed"
# The stops that reach her morning email as well as the digest.
REAUTH = (
    "On the Mac, in how-we-know: .venv/bin/python auth/whisper_youtube_auth.py, pick Whisper Almanac.")
MORNING_CODES = {"WHISPER_YT_TOKEN_INVALID", "UPLOAD_QUOTA", "FRAME_CHECK_FAILED",
                 "WHISPER_UPLOAD_REFUSED", "WHISPER_UPLOAD_FAILED", "WHISPER_UPLOAD_NOT_CONFIRMED"}


def dry_run() -> bool:
    return os.environ.get("LOOP_DRY_RUN") == "1"


def ucfg(c: dict | None = None) -> dict:
    return (c or WL.cfg())["upload"]


# ------------------------------------------------------------------ the kits
def kit_path(slug: str) -> Path:
    return WL.KITS / slug / "kit.json"


def read_kit(slug: str) -> dict:
    p = kit_path(slug)
    return json.loads(p.read_text()) if p.exists() else {}


def write_kit(slug: str, k: dict) -> None:
    kit_path(slug).write_text(json.dumps(k, indent=2, ensure_ascii=False) + "\n")


def kits() -> dict[str, dict]:
    return {f.stem: read_kit(f.stem) for f in WL.all_scripts() if kit_path(f.stem).exists()}


def set_aside(slug: str) -> Path:
    v = WL.video_path(slug)
    return v.with_name(v.name + FAILED)


def candidates(ks: dict[str, dict]) -> list[str]:
    """Rendered, not uploaded, not set aside by a failed frame check; sleep
    episodes first (the lead lane), oldest render first."""
    rows = []
    for slug, k in ks.items():
        v = WL.video_path(slug)
        if k.get("video_id") or not v.exists():
            continue
        rows.append((0 if k.get("kind") == "sleep" else 1, v.stat().st_mtime, slug))
    return [s for *_, s in sorted(rows)]


def fingerprint(video: Path) -> str:
    st = video.stat()
    return f"{st.st_size}:{int(st.st_mtime)}"


# ------------------------------------------------------------------ the checks
def lane_problems(slug: str, k: dict, c: dict) -> list[str]:
    """Every lane check, again, on what is about to go up."""
    out = list(WL.script_problems(WL.SCRIPTS / f"{slug}.md", c=c))
    if k.get("length_basis") != "measured":
        out.append("KIT_LENGTH_NOT_MEASURED the kit was not rewritten from the voiced audio")
    out += WL.meta_problems(k, float(k.get("length_s") or 0), c)
    st = (k.get("body") or {}).get("status") or {}
    if st.get("selfDeclaredMadeForKids") is not False:
        out.append("MADE_FOR_KIDS_NOT_NO")
    if k.get("kind", "sleep") != "sleep":
        # Her call 9 Nov 2026: a manifesting video never goes up with deep-sea
        # footage. visuals/whisper_render.py records the set it rendered with.
        want = c["calm_footage"]["lanes"].get(k.get("lane") or "")
        if not want or k.get("footage_set") != want:
            out.append(f"WRONG_FOOTAGE_SET rendered with {k.get('footage_set') or 'deep-sea footage'}, "
                       f"its lane takes {want}: re-render it")
    return out


def subject(slug: str, c: dict) -> str:
    """What the frames must show: the subjects of the How We Know episodes
    each part was rewritten from (affirmations: their calm footage)."""
    import shot_list                                        # noqa: PLC0415
    p = WL.parse(WL.SCRIPTS / f"{slug}.md")
    fs = WL.footage_set(p, c)
    if fs:                                 # manifesting lanes: their calm footage set
        return (f"{', '.join(WL.footage_subjects(fs, c))} (dimmed for sleep; the video "
                f"is titled {p['title']!r})")
    srcs = [s["source"] for s in p["segments"]]
    subs: list[str] = []
    for s in srcs:
        try:
            got = shot_list.subjects(s)
        except Exception:                                   # noqa: BLE001
            got = []
        # No shot list (measured 9 Nov 2026 on W45: every source had none, so
        # the judge was asked about an EMPTY subject): the episode's own words.
        subs += got or [s.split("-", 1)[-1].replace("-", " ")]
    names = ", ".join(dict.fromkeys(x for x in subs if x))
    return f"{names} (dimmed for sleep; the video is titled {p['title']!r})"


def frame_check(video: Path, slug: str, c: dict) -> dict:
    """visuals/whisper_frame_check.check on the finished file - the sleep
    picture gate, not How We Know's every-frame documentary gate. Raises
    frame_check's PictureCheckFailed / FrameCheckUnavailable."""
    import whisper_frame_check as WFC                       # noqa: PLC0415
    return WFC.check(str(video), subject(slug, c))


# ------------------------------------------------------------------ the calendar
def _utc(s: str | None) -> _dt.datetime | None:
    if not s:
        return None
    t = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=_dt.timezone.utc)


def stamp(t: _dt.datetime) -> str:
    return t.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def waiting_days(kind: str, ks: dict[str, dict], now: _dt.datetime) -> float:
    """Days of this format already uploaded and dated but not yet public."""
    ahead = [t for k in ks.values() if k.get("kind") == kind
             and (t := _utc(k.get("scheduled_publish_at"))) and t > now]
    return max(((t - now).total_seconds() / 86400 for t in ahead), default=0.0)


def days_for(k: dict, c: dict, ks: dict[str, dict] | None = None) -> list[str]:
    """The `upload.days` keys for a kit: its lane when the lane has its own
    days (her decision 9 Nov 2026: Tue food history, Fri ocean documentary),
    else its kind. A finished video never waits for a planned one (9 Nov
    2026): a lane in `share_when_idle` also takes its partner's days while
    the partner has no rendered video waiting to upload (a measured kit
    with no video id)."""
    u = ucfg(c)
    lane = k.get("lane") or ""
    if lane not in u["days"]:
        return [k.get("kind", "sleep")]
    keys = [lane]
    for group in u.get("share_when_idle", []):
        if lane not in group:
            continue
        for other in group:
            if other != lane and other in u["days"] and not any(
                    o.get("lane") == other and o.get("length_basis") == "measured" and not o.get("video_id")
                    for o in (ks or {}).values()):
                keys.append(other)
    return keys


def next_slot(kind: str | list[str], ks: dict[str, dict], now: _dt.datetime, c: dict) -> _dt.datetime:
    """The first free 20:00 Central slot on this format's days (`kind` is an
    `upload.days` key: a lane or a kind, days_for), at least
    `min_lead_hours` away (a 2-hour video needs its processing time)."""
    u = ucfg(c)
    hh, mm = (int(x) for x in u["publish_time_ct"].split(":"))
    days = {DAYS.index(d) for key in ([kind] if isinstance(kind, str) else kind) for d in u["days"][key]}
    taken = {k.get("scheduled_publish_at") for k in ks.values()}
    earliest = now + _dt.timedelta(hours=u["min_lead_hours"])
    d = now.astimezone(CT).date()
    for _ in range(400):
        if d.weekday() in days:
            t = _dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=CT)
            if t >= earliest and stamp(t) not in taken:
                return t
        d += _dt.timedelta(days=1)
    raise RuntimeError(f"no free {kind} slot in 400 days")


# ------------------------------------------------------------------ YouTube
class TokenInvalid(Exception):
    pass


class QuotaSpent(Exception):
    pass


def credentials(c: dict) -> dict | None:
    """The @whisperalmanac grant: .secrets/ on the Mac, else the repo secret
    in the environment. None under LOOP_DRY_RUN, and when neither exists."""
    if dry_run():
        return None
    u = ucfg(c)
    p = ROOT / u["token_file"]
    raw = p.read_text() if p.exists() else os.environ.get(u["token_env"], "")
    try:
        tok = json.loads(raw) if raw.strip() else None
    except ValueError:
        return None
    if not tok or not all(tok.get(k) for k in ("client_id", "client_secret", "refresh_token")):
        return None
    return tok


class YouTube:
    """The live calls. Tests hand run() a fake with the same five methods."""

    def __init__(self, creds: dict):
        import upload as up                                 # noqa: PLC0415
        self._up = up
        try:
            self.token = up.access_token(creds)
        except urllib.error.HTTPError as e:
            raise TokenInvalid(f"Google refused the refresh token (HTTP {e.code}: "
                               f"{e.read().decode('utf-8', 'ignore')[:160]})") from e

    def _get(self, path: str, **q) -> dict:
        req = urllib.request.Request(f"{API}/{path}?{urllib.parse.urlencode(q)}",
                                     headers={"Authorization": f"Bearer {self.token}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())

    def handle(self) -> str:
        items = self._get("channels", part="snippet", mine="true").get("items") or []
        return (items[0]["snippet"].get("customUrl") or "").lower() if items else ""

    def insert(self, body: dict, video: Path) -> str:
        try:
            return self._up.resumable_upload(self.token, body, video)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:600]
            if e.code == 403 and ("quotaExceeded" in detail or "uploadLimitExceeded" in detail):
                raise QuotaSpent(detail) from e
            if e.code == 401:
                raise TokenInvalid(f"YouTube refused the token on upload ({detail[:160]})") from e
            raise RuntimeError(f"HTTP {e.code} {detail}") from e

    def status(self, ids: list[str]) -> dict[str, dict]:
        out = {}
        for it in self._get("videos", part="status,processingDetails", id=",".join(ids)).get("items", []):
            out[it["id"]] = {**it.get("status", {}),
                             "processingStatus": (it.get("processingDetails") or {}).get("processingStatus")}
        return out

    def thumbnail(self, vid: str, png: Path) -> None:
        req = urllib.request.Request(THUMB_URL + vid, data=png.read_bytes(), method="POST",
                                     headers={"Authorization": f"Bearer {self.token}",
                                              "Content-Type": "image/png"})
        urllib.request.urlopen(req, timeout=120).read()


def afford() -> bool:
    import quota                                            # noqa: PLC0415
    return quota.videos_affordable(1, reserve=quota.shorts_reserve()) > 0


def spend(units: int) -> None:
    import quota                                            # noqa: PLC0415
    quota.spend(units, LANE)


def quota_line() -> str:
    try:
        import quota                                        # noqa: PLC0415
        return f"{quota.report()}; resets {quota.next_reset()}"
    except Exception:                                       # noqa: BLE001
        return "the allowance resets at midnight Pacific"


# ------------------------------------------------------------------ the morning line
def morning_line(text: str) -> str:
    """One line in her morning email's Notices (Boss OS addMorningLines, on
    this Mac). Never fails the lane: a line that could not be written is said."""
    if dry_run():
        return "dry run: no morning line"
    boss = Path(os.path.expanduser(os.environ.get("BOSS_OS_REPO") or "~/GitHub/boss-os"))
    mod = boss / "src" / "shared" / "boss" / "mail" / "morning.mjs"
    node = shutil.which("node")
    if not (node and mod.exists()):
        return f"no morning line: {'node' if not node else mod} not found"
    js = (f"import {{ addMorningLines }} from {json.dumps(mod.as_uri())};"
          "addMorningLines('notices', { lines: [{ text: process.argv[1] }] });")
    r = subprocess.run([node, "--input-type=module", "-e", js, text],
                       capture_output=True, text=True, timeout=90)
    return "morning line written" if r.returncode == 0 else f"no morning line: {r.stderr.strip()[-160:]}"


PLAIN = {
    "WHISPER_YT_TOKEN_INVALID": "Whisper Almanac could not sign in to YouTube, so nothing was uploaded. "
                                "On the Mac, in how-we-know: .venv/bin/python auth/whisper_youtube_auth.py "
                                "and pick Whisper Almanac.",
    "UPLOAD_QUOTA": "Whisper Almanac: YouTube's daily upload allowance was used up, so the episode "
                    "goes up on the next night by itself.",
    "FRAME_CHECK_FAILED": "Whisper Almanac: a finished episode failed the picture check, so it was "
                          "not uploaded. It is kept on the Mac, and the next finished episode goes up instead.",
}


# ------------------------------------------------------------------ the lane
def prune_confirmed(yt, ks: dict[str, dict], st) -> int:
    """Delete the local render and voice wavs of every upload YouTube
    reports `processed` with no rejection. Returns how many."""
    rows = {s: k for s, k in ks.items() if k.get("video_id") and not k.get("pruned")}
    if not rows:
        return 0
    got = yt.status([k["video_id"] for k in rows.values()])
    n = 0
    for slug, k in rows.items():
        s = got.get(k["video_id"])
        if not s:
            st.note(f"{slug}: YouTube does not list {k['video_id']}; nothing deleted")
            continue
        if s.get("uploadStatus") != "processed" or s.get("rejectionReason"):
            st.note(f"{slug}: {k['video_id']} is {s.get('uploadStatus')}; render kept until processed")
            continue
        v = WL.video_path(slug)
        freed = v.stat().st_size if v.exists() else 0
        v.unlink(missing_ok=True)
        for w in WL.audio_dir(slug).glob("*.wav"):
            freed += w.stat().st_size
            w.unlink()
        k["pruned"] = {"at": stamp(_dt.datetime.now(_dt.timezone.utc)), "upload_status": "processed",
                       "bytes": freed}
        write_kit(slug, k)
        st.work(f"deleted {slug}'s local render and voice ({freed / 2**30:.2f} GiB): "
                f"YouTube reports {k['video_id']} processed")
        n += 1
    return n


def confirm(yt, vid: str, want: str) -> tuple[dict | None, str]:
    """(status, problem): the id exists, processing has started, private
    with the publish date, the altered-content box set."""
    import publish as P                                     # noqa: PLC0415
    s = None
    for wait in (0, *P.READBACK_WAITS_S):
        P._sleep(wait)
        s = yt.status([vid]).get(vid)
        if s and s.get("uploadStatus") in ("uploaded", "processed") and s.get("publishAt"):
            break
    if not s:
        return None, f"YouTube does not list {vid} after the upload"
    if s.get("uploadStatus") not in ("uploaded", "processed") or s.get("rejectionReason") \
            or s.get("failureReason"):
        return s, f"{vid} is {s.get('uploadStatus')} ({s.get('rejectionReason') or s.get('failureReason')})"
    if s.get("privacyStatus") != "private" or _utc(s.get("publishAt")) != _utc(want):
        return s, (f"{vid} reads {s.get('privacyStatus')} with publishAt {s.get('publishAt')}, "
                   f"not private until {want}")
    if s.get("containsSyntheticMedia") is False:
        return s, f"{vid} reads containsSyntheticMedia=false"
    return s, ""


class Seen:
    """st.named_stop, plus one morning line for the stops in MORNING_CODES."""

    def __init__(self, st, notify):
        self.st, self.notify = st, notify

    def named_stop(self, code, message, unblock="", **kw):
        if code in MORNING_CODES:
            self.st.note(self.notify(PLAIN.get(code) or f"Whisper Almanac: {message[:220]}"))
        self.st.named_stop(code, message, unblock=unblock, **kw)


def run(now: _dt.datetime | None = None, yt=None, checker=None, notify=morning_line) -> int:
    import breaker                                          # noqa: PLC0415
    import common as C                                      # noqa: PLC0415
    breaker.guard(LANE)
    c = WL.cfg()
    now = now or _dt.datetime.now(_dt.timezone.utc)
    checker = checker or frame_check

    with C.Stage(LANE, zero_work_hint="no finished Whisper Almanac episode to upload or confirm") as st:
        out = Seen(st, notify)

        ks = kits()
        todo = candidates(ks)
        pending = [s for s, k in ks.items() if k.get("video_id") and not k.get("pruned")]
        if not todo and not pending:
            st.named_stop("WHISPER_NOTHING_TO_UPLOAD",
                          "no Whisper Almanac episode is rendered and waiting, and every upload "
                          "is confirmed and cleaned up",
                          unblock="Nothing to do: the next rendered episode uploads the night it is made.")
        if yt is None:
            creds = credentials(c)
            if creds is None:
                out.named_stop("WHISPER_YT_TOKEN_INVALID",
                     f"no usable @whisperalmanac token ({ucfg(c)['token_file']} or the "
                     f"{ucfg(c)['token_env']} secret){' - LOOP_DRY_RUN refuses it' if dry_run() else ''}",
                     unblock=REAUTH)
            try:
                yt = YouTube(creds)
            except TokenInvalid as e:
                out.named_stop("WHISPER_YT_TOKEN_INVALID", str(e),
                     unblock=REAUTH)
            except Exception as e:                          # noqa: BLE001
                out.named_stop("WHISPER_UPLOAD_FAILED", f"could not reach Google to sign in: {str(e)[:200]}",
                     unblock="Nothing is lost: the next night tries again.")
        try:
            handle = yt.handle()
        except urllib.error.HTTPError as e:
            out.named_stop("WHISPER_YT_TOKEN_INVALID" if e.code in (401, 403) else "WHISPER_UPLOAD_FAILED",
                 f"YouTube refused the channel read (HTTP {e.code})",
                 unblock=REAUTH)
        if handle != c["channel"]["handle"]:
            out.named_stop("WHISPER_YT_TOKEN_INVALID",
                 f"the token signs in to {handle or 'no channel'}, not {c['channel']['handle']}; nothing uploaded",
                 unblock=REAUTH)
        st.note(f"signed in to {handle}")

        pruned = prune_confirmed(yt, ks, st)

        refused, failed, holds, unavailable = [], [], [], []
        uploaded = 0
        for slug in todo[:ucfg(c)["max_per_run"]]:
            k = ks[slug]
            if WL.retitle(k, c) != k:          # her decision 9 Nov 2026 renamed lanes and titles
                k = WL.retitle(k, c)
                write_kit(slug, k)
                st.note(f"{slug}: retitled for its lane: {k['title']}")
            video = WL.video_path(slug)
            probs = lane_problems(slug, k, c)
            if probs:
                refused.append(f"{slug}: {probs[0]}")
                st.note(f"REFUSE {slug}: {len(probs)} lane check(s) fail: {probs[:3]}")
                continue
            fc = k.get("frame_check") or {}
            if not (fc.get("passed") and fc.get("file") == fingerprint(video)):
                import frame_check as FC                    # noqa: PLC0415
                try:
                    r = checker(video, slug, c)
                except FC.PictureCheckFailed as e:
                    k["frame_check"] = {"passed": False, "file": fingerprint(video),
                                        "at": stamp(now), "why": str(e)[:600]}
                    write_kit(slug, k)
                    video.replace(set_aside(slug))
                    failed.append(f"{slug}: {str(e)[:200]}")
                    st.note(f"{slug} failed the frame check; set aside as {set_aside(slug).name}")
                    continue
                except FC.FrameCheckUnavailable as e:
                    unavailable.append(slug)
                    st.note(f"{slug}: {e}")
                    continue
                k["frame_check"] = {"passed": True, "file": fingerprint(video), "at": stamp(now),
                                    "frames": r.get("frames")}
                write_kit(slug, k)
                st.work(f"{slug}: frame check passed ({r.get('frames')} frames)")
            kind = k.get("kind", "sleep")
            ks_now = kits()
            days = waiting_days(kind, ks_now, now)
            if days >= ucfg(c)["max_days_waiting"]:
                holds.append(f"{slug}: {days:.1f} days of {kind} waiting")
                st.note(f"HOLD {slug}: {days:.1f} days of {kind} already wait on YouTube "
                        f"(the supply gate: under {ucfg(c)['max_days_waiting']}); the render waits")
                continue
            if not afford():
                out.named_stop("UPLOAD_QUOTA", f"no quota left today for {slug} ({UNITS} units). {quota_line()}",
                     unblock="Nothing to do: the allowance resets at midnight Pacific and the next "
                             "night uploads it.", detail={"resets_at": quota_line()})
            when = next_slot(days_for(k, c, ks_now), ks_now, now, c)
            want = stamp(when)
            body = json.loads(json.dumps(k["body"]))
            body["status"].update({"privacyStatus": "private", "publishAt": want,
                                   "containsSyntheticMedia": True,
                                   "selfDeclaredMadeForKids": False})
            try:
                vid = yt.insert(body, video)
            except QuotaSpent as e:
                out.named_stop("UPLOAD_QUOTA", f"YouTube refused {slug}: the daily allowance is spent ({str(e)[:160]})",
                     unblock="Nothing to do: the allowance resets at midnight Pacific and the next "
                             "night uploads it.", detail={"resets_at": quota_line()})
            except TokenInvalid as e:
                out.named_stop("WHISPER_YT_TOKEN_INVALID", str(e),
                     unblock=REAUTH)
            except Exception as e:                          # noqa: BLE001
                out.named_stop("WHISPER_UPLOAD_FAILED", f"{slug} did not upload: {str(e)[:300]}",
                     unblock="Read ~/Library/Logs/how-we-know/batch.log; the render is kept and "
                             "the next night tries again.")
            # Recorded the moment YouTube returns an id, so no later failure
            # can make the next night upload it twice.
            k.update({"uploaded": True, "video_id": vid, "uploaded_at": stamp(now),
                      "privacy": "private", "scheduled_publish_at": want,
                      "publish_at_ct": when.strftime("%a %d %b %Y %H:%M CT")})
            write_kit(slug, k)
            spend(UNITS)
            st.work(f"uploaded {slug} -> {vid} (private, public {k['publish_at_ct']})")
            try:
                yt.thumbnail(vid, WL.KITS / slug / "thumbnail.png")
            except Exception as e:                          # noqa: BLE001
                st.note(f"thumbnail not set on {vid} ({str(e)[:120]}); the video is up and dated")
            s, why = confirm(yt, vid, want)
            if why:
                out.named_stop("WHISPER_UPLOAD_NOT_CONFIRMED", why, detail={"slug": slug, "video_id": vid},
                     unblock="Open the video in YouTube Studio; the local render is kept.")
            k["youtube_confirmed"] = {"at": stamp(_dt.datetime.now(_dt.timezone.utc)),
                                      "upload_status": s.get("uploadStatus"),
                                      "processing": s.get("processingStatus")}
            write_kit(slug, k)
            uploaded += 1
            st.work(f"YouTube confirms {vid}: {s.get('uploadStatus')}, private until {want}")

        if failed:
            out.named_stop("FRAME_CHECK_FAILED",
                 f"{len(failed)} finished episode(s) failed the final frame check and were not "
                 f"uploaded: {'; '.join(failed)}",
                 detail={"failed": failed}, held_items=[f.split(":")[0] for f in failed],
                 unblock="Each file is set aside beside its render (never deleted); a footage fix and "
                         "a re-render (delete the set-aside file) put it back in line.")
        if refused:
            out.named_stop("WHISPER_UPLOAD_REFUSED",
                 f"{len(refused)} finished episode(s) fail a lane check and were not uploaded: "
                 f"{'; '.join(refused)}", detail={"refused": refused},
                 unblock="Fix the rule or the kit named; the render is kept.")
        if not uploaded and not pruned:
            if holds:
                st.named_stop("WHISPER_UPLOAD_HOLD",
                              f"the supply gate holds: {'; '.join(holds)} (at most "
                              f"{ucfg(c)['max_days_waiting']} days of a format wait on YouTube)",
                              unblock="Nothing to do: the gate opens as the scheduled episodes go public.")
            if unavailable:
                st.named_stop("FRAME_CHECK_UNAVAILABLE",
                              f"no free vision model answered the frame check for {', '.join(unavailable)}; "
                              f"nothing uploaded unchecked",
                              unblock="Nothing to do: the next night checks it again.")
            st.named_stop("WHISPER_AWAITING_PROCESSING",
                          f"{len(pending)} upload(s) are on YouTube and still processing; their local "
                          f"renders are kept until YouTube reports them processed",
                          unblock="Nothing to do: the next night deletes them once processed.")
        print(f"OUTPUT {uploaded} Whisper Almanac episode(s) uploaded and scheduled")
    return 0


def plan() -> int:
    c = WL.cfg()
    now = _dt.datetime.now(_dt.timezone.utc)
    ks = kits()
    todo = candidates(ks)
    for slug in todo:
        kind = ks[slug].get("kind", "sleep")
        k = WL.retitle(ks[slug], c)
        print(f"{slug}: {k.get('lane') or kind}, next slot "
              f"{next_slot(days_for(k, c, ks), ks, now, c).strftime('%a %d %b %H:%M CT')}, title {k['title']!r}, "
              f"{waiting_days(kind, ks, now):.1f} days of {kind} waiting")
    print(f"OUTPUT {len(todo)} Whisper Almanac episode(s) ready to upload")
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
