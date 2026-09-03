"""How long a video actually is — the one place any lane may ask.

Before this module there were three answers to "how long is an episode?" and
none of them was the video:

    loop/config.json  retention.runtime_minutes = 10.5   what retention was divided by
    loop/author.py    150 wpm                            what scripts were written to
    renders/*.mp4                                        what viewers actually watched

The third one is the only one that is true. Measured across the 17 finished
episodes on 2026-09-03 the real durations run 7m32s to 8m56s, mean **8.12
minutes** — so dividing an average view duration by a configured 10.5 reported
**77% of the true retention**: a real 39% displayed as 30%, straight through a
30% floor and into the circuit breaker, on a format that was fine.

The rule this module exists to enforce: **a percentage is only ever computed
against the duration of the specific video it describes.** A constant runtime
is not an approximation of that, it is a different number.

Two persisted files, both committed, because `renders/*.mp4` is gitignored and
the cloud lanes never see the bytes:

    loop/state/durations.json      slug -> measured seconds, and where it came from
    loop/state/runtime_model.json  the DERIVED words-per-minute of the voice

`runtime_model.json` is the answer to "no runtime estimate anywhere computed
from a hardcoded speaking rate". Nothing in this repo may hardcode a wpm; it
asks here, and this module refuses to guess when it has not measured.

Refresh both on a machine that has the renders:

    .venv/bin/python loop/durations.py --refresh
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "loop"))

RENDERS = ROOT / "renders"
SCRIPTS = ROOT / "scripts"
DURATIONS = ROOT / "loop" / "state" / "durations.json"
RUNTIME_MODEL = ROOT / "loop" / "state" / "runtime_model.json"

# Below this many measured episodes the derived rate is noise, not evidence.
# Nine is the point at which one outlier cannot move the pooled rate by more
# than a couple of percent; the current corpus supplies seventeen.
MIN_EPISODES_FOR_MODEL = 9


class NotMeasured(Exception):
    """Asked for a measured value that has never been measured.

    Always a NAMED STOP at the calling stage, never a fallback to a guess — a
    guessed runtime is the defect this module was written to delete.
    """


# --------------------------------------------------------------- ffprobe

def ffprobe_duration(path: Path) -> float | None:
    """Seconds, from the container. None if ffprobe is absent or the file is not
    readable — the caller must treat that as unknown, never as zero."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=60)
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    out = (r.stdout or "").strip()
    try:
        return float(out)
    except ValueError:
        return None


def render_path(slug: str) -> Path | None:
    """The file that is actually UPLOADED.

    `loop/r2.py` shelves `renders/<slug>-final.mp4` and `loop/cloud_upload.py`
    fetches exactly that key, so `-final.mp4` is the published video and the
    bare `<slug>.mp4` beside it is an earlier cut. Measuring the wrong one is
    how a 7m32s "runtime" gets attributed to an 8m56s video.
    """
    p = RENDERS / f"{slug}-final.mp4"
    return p if p.exists() else None


# ------------------------------------------------------------ the store

def _load(path: Path, default: dict) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return dict(default)


def load() -> dict:
    return _load(DURATIONS, {"episodes": {}, "updated": None})


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def record(slug: str, seconds: float, source: str,
           narration_words_at_measurement: int | None = None) -> float:
    """Persist a measured duration. Called by the upload lane at upload time,
    which is the last moment the bytes and the repo are in the same place.

    `narration_words_at_measurement`, once set, is NEVER overwritten by a
    later call for the same slug (see below) — it freezes the word count that
    was actually spoken in THIS render, at the moment the render was measured.
    """
    d = load()
    existing = d["episodes"].get(slug, {})
    rec = {"seconds": round(float(seconds), 3), "source": source}
    # Freeze once, keep forever. A script's ## Narration text can be edited
    # after an episode is already rendered (captions/voice fixes, the
    # 2026-09-03 boilerplate-and-second-person rewrite) without the audio
    # being re-recorded - confirmed 2026-09-03: that rewrite alone moved
    # ep01's word count from 1149 (what the render actually says) to 1118
    # (what scripts/01....md now says), and a bare `--refresh` after it
    # silently recomputed the model's wpm from the WRONG, edited-down count
    # against the unchanged old audio (144.58 -> 142.38, one episode's wpm
    # dropping to 129.18 - a wrong number nothing would have checked, the
    # exact defect class this module exists to delete). The fix is that the
    # word count a render's wpm is measured against must be captured once,
    # at measurement time, and never re-derived from whatever text happens
    # to be in scripts/*.md later.
    if existing.get("narration_words_at_measurement"):
        rec["narration_words_at_measurement"] = existing["narration_words_at_measurement"]
    elif narration_words_at_measurement:
        rec["narration_words_at_measurement"] = int(narration_words_at_measurement)
    d["episodes"][slug] = rec
    from common import now                                  # noqa: PLC0415
    d["updated"] = now()
    _save(DURATIONS, d)
    return round(float(seconds), 3)


def duration_s(slug: str, probe: bool = True) -> float | None:
    """Actual seconds for one episode, or None if it has never been measured.

    Order: the duration recorded at upload, then the render on this machine.
    Never a configured constant, and never an estimate from word count.
    """
    rec = load()["episodes"].get(slug)
    if rec and rec.get("seconds"):
        return float(rec["seconds"])
    if probe:
        p = render_path(slug)
        if p:
            s = ffprobe_duration(p)
            if s:
                # Capture the narration word count THIS MOMENT, alongside the
                # duration it actually produced - see record()'s docstring.
                # A slug probed here for the first time has never had a
                # chance to drift from its own audio yet, so "whatever
                # scripts/<slug>.md says right now" is still ground truth.
                return record(slug, s, f"ffprobe {p.name}",
                             narration_words_at_measurement=narration_words(slug))
    return None


def known() -> dict[str, float]:
    return {k: float(v["seconds"]) for k, v in load()["episodes"].items()
            if v.get("seconds")}


# ------------------------------------------------- narration and the model

DIRECTIVE = re.compile(r"\{\{.*?\}\}", re.S)


def narration_words(slug: str) -> int | None:
    """Words a voice actually speaks: `## Narration`, directives and headings
    removed. This is the only word count that becomes runtime."""
    p = SCRIPTS / f"{slug}.md"
    if not p.exists():
        return None
    return narration_words_of(p.read_text(encoding="utf-8"))


def narration_words_of(text: str) -> int:
    m = re.search(r"## Narration\s*\n(.*?)(\n## |\Z)", text, re.S)
    if not m:
        return 0
    body = DIRECTIVE.sub(" ", m.group(1))
    body = "\n".join(l for l in body.splitlines()
                     if not l.strip().startswith("#"))
    return len(body.replace("[HUMAN]", " ").split())


def total_words_of(text: str) -> int:
    return len(text.split())


def measure_model() -> dict:
    """Derive the voice's words-per-minute from every episode that has BOTH a
    narration word count and a measured render. Nothing here is assumed.

    The word count paired with each render's duration comes from
    `loop/state/durations.json`'s FROZEN `narration_words_at_measurement`
    when one exists - never from re-reading scripts/*.md, which can (and on
    2026-09-03, did) drift after the render was made. A slug measured for the
    first time here freezes its current word count via `record()` so it
    cannot drift out from under its own already-recorded audio later either.
    """
    rows, words, secs, tot = [], 0, 0.0, 0
    for p in sorted(SCRIPTS.glob("*.md")):
        slug = p.stem
        d = duration_s(slug)
        if not d:
            continue
        text = p.read_text(encoding="utf-8")
        stored = load()["episodes"].get(slug, {})
        frozen_w = stored.get("narration_words_at_measurement")
        if frozen_w:
            w = int(frozen_w)
        else:
            w = narration_words_of(text)
            if w:
                # First time this slug is entering the model - freeze it now,
                # against the source string used for the recorded seconds.
                record(slug, d, stored.get("source", "unrefreshed"),
                      narration_words_at_measurement=w)
        if not w:
            continue
        rows.append({"slug": slug, "narration_words": w,
                     "duration_s": round(d, 3),
                     "wpm": round(w / (d / 60), 2)})
        words += w
        secs += d
        tot += total_words_of(text)
    if len(rows) < MIN_EPISODES_FOR_MODEL:
        raise NotMeasured(
            f"only {len(rows)} episode(s) have both a narration word count and "
            f"a measured render; {MIN_EPISODES_FOR_MODEL} are needed before a "
            f"speaking rate is evidence rather than an average of noise. Run "
            f"this on a machine that has renders/*-final.mp4.")
    from common import now                                  # noqa: PLC0415
    return {
        "wpm": round(words / (secs / 60), 2),
        "script_ratio": round(tot / words, 4),
        "episodes": len(rows),
        "narration_words_total": words,
        "measured_seconds_total": round(secs, 2),
        "mean_runtime_s": round(secs / len(rows), 2),
        "wpm_range": [min(r["wpm"] for r in rows), max(r["wpm"] for r in rows)],
        "measured_at": now(),
        "per_episode": rows,
        "note": ("Derived, never hardcoded. wpm = spoken narration words / "
                 "measured render minutes across every episode that has both. "
                 "script_ratio is whole-script words : narration words, which "
                 "is what a whole-script budget has to be divided by before it "
                 "means anything about runtime."),
    }


def model(refresh: bool = False) -> dict:
    """The derived runtime model. Reads the committed cache in the cloud, where
    renders/ does not exist; re-derives on a machine that has the bytes."""
    if not refresh:
        cached = _load(RUNTIME_MODEL, {})
        if cached.get("wpm"):
            return cached
    m = measure_model()
    _save(RUNTIME_MODEL, m)
    return m


def wpm() -> float:
    """Measured words per minute. Raises rather than guessing."""
    m = model()
    if not m.get("wpm"):
        raise NotMeasured("loop/state/runtime_model.json has no measured wpm; "
                          "run `loop/durations.py --refresh` where the renders "
                          "are")
    return float(m["wpm"])


def narration_words_for(minutes: float) -> int:
    """How many spoken words a target runtime needs, at the MEASURED rate."""
    return int(round(float(minutes) * wpm()))


def minutes_for(words: int) -> float:
    return round(int(words) / wpm(), 2)


# ------------------------------------------------------------------- cli

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true",
                    help="re-probe every render and re-derive the runtime model")
    a = ap.parse_args()

    if a.refresh:
        found = 0
        for p in sorted(SCRIPTS.glob("*.md")):
            r = render_path(p.stem)
            if not r:
                continue
            s = ffprobe_duration(r)
            if s:
                record(p.stem, s, f"ffprobe {r.name}")
                found += 1
        if not found:
            print("FAIL: probed zero renders — refreshed nothing. "
                  "renders/*-final.mp4 is gitignored; run this on the Mac.")
            return 1
        print(f"measured {found} render(s) -> {DURATIONS.relative_to(ROOT)}")

    try:
        m = model(refresh=a.refresh)
    except NotMeasured as e:
        print(f"FAIL: {e}")
        return 1
    print(f"{m['episodes']} episode(s) measured")
    print(f"  wpm           {m['wpm']}  (range {m['wpm_range'][0]}-{m['wpm_range'][1]})")
    print(f"  script_ratio  {m['script_ratio']}")
    print(f"  mean runtime  {m['mean_runtime_s'] / 60:.2f} min")
    print(f"  10.0 min needs {narration_words_for(10.0)} spoken words")
    print(f"  10.5 min needs {narration_words_for(10.5)} spoken words")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
