"""The food videos' low sound layer: sizzle, snap and pour, ducked under the voice.

    .venv/bin/python visuals/food_sound.py harvest     # fetch + rights-check the sounds
    .venv/bin/python visuals/food_sound.py --verify    # sha256 + licence on disk
    .venv/bin/python visuals/food_sound.py ensure      # fetch any missing (food nights do)

SOURCES. Wikimedia Commons recordings that pass the SAME licence gate as the
pictures (research/imagery.pd_licence_ok: public domain or CC0 only, read live
from the item page; research/imagery_materials.copyright_asserted screens the
item's own prose). The YouTube Audio Library has no API and needs her login,
so it is not used; Commons CC0/PD is a free library that this Mac can reach.
Each file is recorded in channel/sound/food.json with its item page, licence
and sha256, and the files themselves stay out of git (channel/sound/*.ogg).

THE MIX (owner's brief, 2026-10-13): low, under the narration, never over it.
Each shot gets the cue its picture implies (a pour under liquid chocolate, a
sizzle under a sear, a snap at a break), laid at BED_DB, then ducked by a
sidechain compressor keyed on the voice. duck_and_mix() MEASURES the result
on the rendered audio - bed level inside speech vs in the pauses, and voice
over bed - and CONTRACT is checked on those numbers (validator V54,
loop/tests/test_food_voice_sound.py).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOUND = ROOT / "channel" / "sound"
MANIFEST = SOUND / "food.json"
SR = 48000

# Hand-picked Commons recordings; each still has to pass the live gate.
SOUNDS = {
    "sizzle": "File:Frying fries going in and out of oil.ogg",
    "pour": "File:Pouring water in mug in sink.ogg",
    "snap": "File:Cracking peanuts.ogg",
}
# picture -> cue. Keys are visuals/food.py asset keys.
CUE_FOR = {
    "sizzle": ("steak", "sear", "crust", "grill"),
    "pour": ("chocolate-sheets", "chocolate-river", "chocolate-ocean", "melt",
             "pour", "tempering", "liquid"),
    "snap": ("snap", "break"),
}
BED_DB = -26.0                    # cue level before ducking (dBFS RMS)
CONTRACT = {
    "duck_db_at_least": 6.0,          # bed drops this much while she speaks
    "voice_over_bed_db_at_least": 15.0,
    "bed_in_gaps_db_above": -60.0,    # and it is really there in the pauses
    "peak_dbfs_at_most": -1.0,
}


def harvest() -> dict:
    sys.path.insert(0, str(ROOT / "research"))
    import imagery as I                                       # noqa: PLC0415
    import imagery_materials as M                              # noqa: PLC0415
    SOUND.mkdir(parents=True, exist_ok=True)
    index = []
    for key, title in SOUNDS.items():
        iq = (f"{M.COMMONS_API}?action=query&format=json&prop=imageinfo"
              f"&iiprop=url|size|mime|extmetadata&titles=" + urllib.parse.quote(title))
        info = next(iter(json.loads(M._polite(iq))["query"]["pages"].values()))["imageinfo"][0]
        ok, why = I.pd_licence_ok(info)
        claimed, why_c = M.copyright_asserted(info)
        if not ok or claimed:
            raise SystemExit(f"NAMED STOP [SOUND_RIGHTS_REFUSED]: {title}: {why if not ok else why_c}")
        blob = M._polite(info["url"], binary=True)
        fname = f"food_sound__{key}.ogg"
        (SOUND / fname).write_bytes(blob)
        licence = str(info.get("extmetadata", {}).get("LicenseShortName", {}).get("value", ""))
        index.append({"key": key, "title": title.removeprefix("File:"),
                      "item_url": info.get("descriptionurl"), "licence": licence,
                      "licence_basis": why, "local_file": fname,
                      "sha256": hashlib.sha256(blob).hexdigest(),
                      "duration_s": info.get("duration")})
    man = {"policy": "Public domain or CC0 only, verified live at the Commons item page "
                     "(research/imagery.pd_licence_ok).", "index": index}
    MANIFEST.write_text(json.dumps(man, indent=2) + "\n")
    return man


def verify() -> int:
    man = json.loads(MANIFEST.read_text())
    n = 0
    for r in man["index"]:
        p = SOUND / r["local_file"]
        if not p.exists():
            raise AssertionError(f"{r['local_file']} not on disk - run harvest")
        if hashlib.sha256(p.read_bytes()).hexdigest() != r["sha256"]:
            raise AssertionError(f"{r['local_file']}: sha256 changed since rights check")
        if not r.get("licence") or not r.get("item_url"):
            raise AssertionError(f"{r['key']}: missing licence or item page")
        n += 1
    if n == 0:
        raise AssertionError("verified zero sounds")
    return n


class SoundMissing(RuntimeError):
    """A bed sound the food preset can pick is not on disk (or not the file
    whose rights were checked). The message names the file."""


def _fetch_one(rec: dict) -> bytes:
    """One manifest recording, fetched from its Commons item through the same
    live licence gate harvest() uses. The manifest is NOT rewritten: the bytes
    must hash to the sha256 recorded when the rights were checked."""
    sys.path.insert(0, str(ROOT / "research"))
    import imagery as I                                       # noqa: PLC0415
    import imagery_materials as M                              # noqa: PLC0415
    title = "File:" + rec["title"].removeprefix("File:")
    iq = (f"{M.COMMONS_API}?action=query&format=json&prop=imageinfo"
          f"&iiprop=url|size|mime|extmetadata&titles=" + urllib.parse.quote(title))
    info = next(iter(json.loads(M._polite(iq))["query"]["pages"].values()))["imageinfo"][0]
    ok, why = I.pd_licence_ok(info)
    claimed, why_c = M.copyright_asserted(info)
    if not ok or claimed:
        raise SoundMissing(f"{title}: licence gate refused it ({why if not ok else why_c})")
    return M._polite(info["url"], binary=True)


def ensure(fetch=None) -> list[str]:
    """Every sound the food preset can pick (SOUNDS, CUE_FOR) is on disk and is
    the file whose rights were checked; a missing one is fetched. The .ogg files
    are gitignored, so a checkout that never ran harvest (this Mac's main
    checkout: the 13 Oct harvest ran in a worktree) has none of them - the
    25 Oct food night rendered for five hours and then died on the sizzle.
    Raises SoundMissing naming the file; returns the files it fetched."""
    fetch = fetch or _fetch_one
    recs = {r["key"]: r for r in json.loads(MANIFEST.read_text())["index"]}
    keys = sorted(set(SOUNDS) | set(CUE_FOR))
    if not keys:
        raise SoundMissing("the food preset lists zero sounds")
    fetched = []
    for key in keys:
        rec = recs.get(key)
        if not rec:
            raise SoundMissing(f"sound '{key}' has no record in channel/sound/food.json")
        p = SOUND / rec["local_file"]
        rel = f"channel/sound/{rec['local_file']}"
        if p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == rec["sha256"]:
            continue
        try:
            blob = fetch(rec)
        except SoundMissing:
            raise
        except Exception as exc:                              # noqa: BLE001
            raise SoundMissing(f"{rel} is not on disk and the fetch from "
                               f"{rec.get('item_url')} failed: {exc}") from exc
        got = hashlib.sha256(blob).hexdigest()
        if got != rec["sha256"]:
            raise SoundMissing(f"{rel}: the Commons file now hashes {got[:12]}, not the "
                               f"{rec['sha256'][:12]} whose rights were checked")
        SOUND.mkdir(parents=True, exist_ok=True)
        p.write_bytes(blob)
        fetched.append(rel)
    return fetched


def cue_for(asset: str | None) -> str | None:
    a = (asset or "").lower()
    for cue, words in CUE_FOR.items():
        if any(w in a for w in words):
            return cue
    return None


def _load(key: str) -> np.ndarray:
    rec = next((r for r in json.loads(MANIFEST.read_text())["index"] if r["key"] == key), None)
    if rec is None:
        raise SoundMissing(f"sound '{key}' has no record in channel/sound/food.json")
    if not (SOUND / rec["local_file"]).exists():
        raise SoundMissing(f"channel/sound/{rec['local_file']} is not on disk "
                           f"(visuals/food_sound.py ensure fetches it)")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(SOUND / rec["local_file"]),
                          "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32).copy()
    rms = float(np.sqrt(np.mean(x ** 2)) + 1e-9)
    return x * (10 ** (BED_DB / 20) / rms)


def _write_wav(path: Path, x: np.ndarray, sr: int = SR) -> None:
    import wave                                               # noqa: PLC0415
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def _read_wav(path: Path) -> np.ndarray:
    import wave                                               # noqa: PLC0415
    with wave.open(str(path)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768.0


def shot_cue(s: dict, cat: dict | None) -> str | None:
    """The cue a shot's PICTURE implies. A real clip carries its own (research/
    food_footage.SHOTS `sound`: a pour under pours, snaps under breaking bars and
    a bite, silence under still heaps); anything else falls back to its key."""
    rec = (cat or {}).get(s.get("asset") or "") or {}
    if rec.get("kind") == "clip":
        return rec.get("sound")
    if s.get("kind") == "device":
        return None
    return cue_for(s.get("asset"))


SNAP_EVERY_S = 1.6               # broken pieces tumbling: a snap now and then, not one


def build_bed(timeline: dict, out: Path, cat: dict | None = None) -> Path:
    """One cue per shot, matched to what is on screen, at BED_DB: pours looped
    and faded (a composite wall of pours a little fuller), snaps as one-shots
    spaced through the shot."""
    n = int(timeline["duration"] * SR) + SR
    bed = np.zeros(n, np.float32)
    src = {k: _load(k) for k in SOUNDS}
    fade = int(0.8 * SR)
    for s in timeline["shots"]:
        cue = shot_cue(s, cat)
        if not cue:
            continue
        a, L = int(s["start"] * SR), int(s["dur"] * SR)
        x = src[cue]
        if cue == "snap":
            one = x[:min(len(x), int(1.2 * SR))].copy()
            seg = np.zeros(L, np.float32)
            for k, at in enumerate(np.arange(0.3, s["dur"] - 0.6, SNAP_EVERY_S)):
                j = int(at * SR)
                o = one[(k * int(0.37 * SR)) % max(1, len(one) // 2):][:L - j]
                seg[j:j + len(o)] += o * (0.8 if k else 1.0)
        else:
            reps = int(np.ceil(L / len(x)))
            seg = np.tile(x, reps)[:L].copy()
        if s.get("treatment") == "wall" and cue == "pour":
            seg = seg * 1.4                            # a wall of pours sounds fuller
        env = np.ones(len(seg), np.float32)
        f = 0 if cue == "snap" else min(fade, len(seg) // 3)
        if f > 0:
            env[:f] = np.linspace(0, 1, f)
            env[-f:] = np.linspace(1, 0, f)
        seg *= env
        bed[a:a + len(seg)] += seg[:max(0, n - a)]
    _write_wav(out, bed)
    return out


def _env_db(x: np.ndarray, hop: int) -> np.ndarray:
    k = len(x) // hop
    fr = x[:k * hop].reshape(k, hop)
    return 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9)


def measure(voice: np.ndarray, bed: np.ndarray, mix: np.ndarray) -> dict:
    hop = int(0.05 * SR)
    n = min(len(voice), len(bed), len(mix))
    v, b = _env_db(voice[:n], hop), _env_db(bed[:n], hop)
    speech = v > -40
    gaps = (~speech) & (b > -90)
    out = {
        "bed_db_in_speech": round(float(np.median(b[speech & (b > -90)])), 2) if (speech & (b > -90)).any() else None,
        "bed_db_in_gaps": round(float(np.median(b[gaps])), 2) if gaps.any() else None,
        "voice_db_in_speech": round(float(np.median(v[speech])), 2) if speech.any() else None,
        "peak_dbfs": round(float(20 * np.log10(np.abs(mix).max() + 1e-9)), 2),
    }
    if out["bed_db_in_speech"] is not None and out["bed_db_in_gaps"] is not None:
        out["duck_db"] = round(out["bed_db_in_gaps"] - out["bed_db_in_speech"], 2)
    if out["bed_db_in_speech"] is not None and out["voice_db_in_speech"] is not None:
        out["voice_over_bed_db"] = round(out["voice_db_in_speech"] - out["bed_db_in_speech"], 2)
    return out


def check(m: dict, c: dict | None = None) -> list[str]:
    c = c or CONTRACT
    p = []
    if m.get("duck_db") is None or m["duck_db"] < c["duck_db_at_least"]:
        p.append(f"bed ducks {m.get('duck_db')} dB under the voice, needs {c['duck_db_at_least']}")
    if m.get("voice_over_bed_db") is None or m["voice_over_bed_db"] < c["voice_over_bed_db_at_least"]:
        p.append(f"voice sits {m.get('voice_over_bed_db')} dB over the bed, needs "
                 f"{c['voice_over_bed_db_at_least']}")
    if m.get("bed_db_in_gaps") is None or m["bed_db_in_gaps"] < c["bed_in_gaps_db_above"]:
        p.append(f"bed is {m.get('bed_db_in_gaps')} dB in the pauses - not really there")
    if m["peak_dbfs"] > c["peak_dbfs_at_most"]:
        p.append(f"mix peaks at {m['peak_dbfs']} dBFS")
    return p


def duck_and_mix(voice: Path, bed: Path, work: Path) -> dict:
    """Sidechain-duck the bed under the voice, mix, measure, refuse if wrong."""
    ducked, mix = work / "bed_ducked.wav", work / "mix.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(bed), "-i", str(voice),
                    "-filter_complex",
                    "[1:a]aresample=48000[sc];"
                    "[0:a]aresample=48000[b];"
                    "[b][sc]sidechaincompress=threshold=0.008:ratio=12:attack=15:"
                    "release=450:makeup=1[d]",
                    "-map", "[d]", "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le",
                    str(ducked)], check=True)
    v = _read_wav(voice)
    d = _read_wav(ducked)
    n = min(len(v), len(d))
    m = v[:n] * 0.92 + d[:n]
    pk = float(np.abs(m).max())
    if pk > 0.89:
        m = m * (0.89 / pk)
    _write_wav(mix, m)
    meas = measure(v[:n], d[:n], m)
    meas["contract_problems"] = check(meas)
    return {"mix": mix, "measured": meas}


if __name__ == "__main__":
    if "ensure" in sys.argv:
        print(f"food sounds on disk; fetched: {ensure() or 'none'}")
    elif "--verify" in sys.argv:
        print(f"food sounds verified: {verify()}")
    elif "harvest" in sys.argv:
        print(json.dumps(harvest(), indent=1)[:800])
