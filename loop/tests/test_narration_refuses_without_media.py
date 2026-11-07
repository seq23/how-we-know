"""A checkout that never received its media must not narrate, and must not
strip a single measured duration.

CONFIRMED 2026-11-07. From 4 Nov the Mac jobs ran in ~/GitHub/.hwk-runner, a
fresh clone with no wavs and no renders (both gitignored). The nightly batch
queued all 81 episodes for re-narration, voice/narrate_all.py dropped `seconds`
from all 60 manifests because each wav was "missing", and the backfill pushed
them (c69c59d). Main went red: no episode carried a measured timing, so no
caption track could be built in the cloud.

Proves, on a scratch audio tree:
  (a) an episode measured on every beat, unchanged plan, zero wavs  -> named;
  (b) the same episode with ONE wav present                          -> not named
      (a checkout with its media, missing a beat, narrates that beat);
  (c) a beat whose words changed (pov_repair's rewrite)              -> not named
      (that duration is rightly dropped and the beat re-voiced);
  (d) a manifest with an unmeasured beat                             -> not named;
  (e) voice/narrate_all.py calls the check and returns before its first
      manifest write (it cannot be imported outside the TTS venv, so its
      source order is checked).
Hard-fails when the scratch case set examined is empty.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "visuals"))

import captions as CAP                                          # noqa: E402

fails: list[str] = []
PLAN = [{"segment": "hook", "narration": "A fish that is not deformed."},
        {"segment": "body", "narration": "Pressure, darkness, and us."}]


def episode(audio: Path, slug: str, rows: list, wavs: list[int]) -> None:
    (audio / slug).mkdir(parents=True)
    CAP.write_beats_manifest(audio / slug / "beats.json", rows)
    for i in wavs:
        (audio / slug / f"{i:04d}.wav").write_bytes(b"RIFF")


def measured(plan: list) -> list:
    return [{"i": i, **b, "seconds": 3.0 + i} for i, b in enumerate(plan)]


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        audio = Path(td)
        episode(audio, "no-media", measured(PLAN), [])
        episode(audio, "one-wav", measured(PLAN), [1])
        changed = [dict(r) for r in measured(PLAN)]
        changed[1]["narration"] = "Words nobody will say again."
        episode(audio, "rewritten", changed, [])
        part = measured(PLAN)
        del part[1]["seconds"]
        episode(audio, "unmeasured", part, [])
        plans = {s: PLAN for s in ("no-media", "one-wav", "rewritten", "unmeasured")}
        got = CAP.measured_audio_absent(plans, audio)
        if not plans:
            fails.append("examined zero cases")
        if got != ["no-media"]:
            fails.append(f"measured_audio_absent named {got}, want ['no-media']")
        # the manifests themselves were not touched by the check
        if "seconds" not in json.loads((audio / "no-media" / "beats.json").read_text())[0]:
            fails.append("the check rewrote a manifest")

    src = Path(ROOT, "voice", "narrate_all.py").read_text()
    call = src.find("measured_audio_absent(plans")
    first_write = src.find("write_beats_manifest(mf")
    ret = src.find("return 3", call)
    if call < 0 or first_write < 0 or not (call < ret < first_write):
        fails.append("voice/narrate_all.py does not refuse (return 3) on "
                     "measured_audio_absent before its first manifest write")

    if fails:
        print("FAIL:\n  - " + "\n  - ".join(fails))
        return 1
    print("PASS: a media-less checkout is named before any manifest is written; "
          "4 cases, 1 named")
    return 0


if __name__ == "__main__":
    sys.exit(main())
