"""A footage render remakes the kit's thumbnails on frames of the video it made.

The thumbnails are drawn at kit time, before the footage exists (the candle
glow). visuals/whisper_render.render() is driven here on its real path, with
only the footage library, the reel planner and the disk guard stubbed, and a
real ffmpeg reel: once it has rendered, thumbnail.png must be the one drawn on
a frame of that video, not the candle. A proof render (--seconds) and an
uploaded kit keep theirs. Hard-fails on zero checks.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "loop"))
sys.path.insert(0, str(ROOT / "visuals"))
os.environ["LOOP_DRY_RUN"] = "1"

import whisper_lane as WL                                   # noqa: E402
import whisper_render as WR                                 # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="whisper-render-thumbs-"))
WL.KITS, WL.WORK = TMP / "kits", TMP / "work"
WR.ROOT = TMP                                                # its log line prints paths relative to this
C = WL.cfg()
SLUG = "the-bottom-of-the-ocean"                             # a footage (sleep) lane script
SECS = 12.0
fails: list[str] = []
examined = 0


def check(name, ok, why=""):
    global examined
    examined += 1
    print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    if not ok:
        fails.append(f"{name}: {why}")


def ff(*a):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *a], check=True)


# the voice: one real wav, measured by the real measured()
wav = TMP / "voice.wav"
ff("-f", "lavfi", "-i", f"sine=f=220:d={SECS}", str(wav))
WR.measured = lambda slug, p, need_all=True: ([wav], SECS, [0.0], {0: SECS})


def render_reel(shots, out, voice, td):                      # a dim, moving, real reel
    ff("-f", "lavfi", "-i", f"testsrc2=s=1280x720:r=10:d={SECS},eq=brightness=-0.35", "-i", str(voice),
       "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out))


class FootageThin(Exception):
    pass


sys.modules["render_prune"] = types.SimpleNamespace(guard=lambda: (0, "disk ok"))
sys.modules["footage"] = types.SimpleNamespace(usable_assets=lambda: [], prefetch=lambda xs: None)
sys.modules["whisper_reel"] = types.SimpleNamespace(
    food_part=lambda s: False, FootageThin=FootageThin, pool=lambda s, a, c: [],
    plan_reel=lambda segs, assets, pool_of: [{"t0": 0.0, "seconds": SECS, "asset": {"post_id": "x"}}],
    reel_problems=lambda shots, total: [], credits=lambda shots: ["Footage: a test clip."],
    render_reel=render_reel)

p = WL.parse(WL.SCRIPTS / f"{SLUG}.md")
check("the script renders with footage", WL.picture_for(SLUG, p, C) == "footage", WL.picture_for(SLUG, p, C))
kit_dir = WL.KITS / SLUG
WL.kit(SLUG, measured_s=SECS, c=C)
candle = (kit_dir / "thumbnail.png").read_bytes()

# a proof render keeps the kit's thumbnails (it is not the video that will go out)
WR.render(SLUG, proof_seconds=SECS)
check("a proof render leaves the thumbnails alone", (kit_dir / "thumbnail.png").read_bytes() == candle)

out = WR.render(SLUG)
frame = WL._frame_at(out, SECS * WL.VARIANTS["a"][1])
want = WL.thumbnail(p, SECS, TMP / "want.png", C, "a", frame)
got = (kit_dir / "thumbnail.png").read_bytes()
check("after the render thumbnail.png is drawn on a frame of the rendered video",
      frame is not None and got == want.read_bytes() and got != candle)
k = json.loads((kit_dir / "kit.json").read_text())
check("the kit records the remade thumbnails and their check",
      k.get("thumbnails") == list(WL.VARIANT_FILES.values()) and "thumbnail_problems" in k, k.get("thumbnails"))

# an uploaded kit: a re-render never changes what was published
k["video_id"] = "PUB1"
(kit_dir / "kit.json").write_text(json.dumps(k))
for name in WL.VARIANT_FILES.values():
    (kit_dir / name).write_bytes(candle)
WR.render(SLUG)
check("an uploaded video's thumbnails stay the published ones",
      all((kit_dir / n).read_bytes() == candle for n in WL.VARIANT_FILES.values()))

if not examined:
    print("FAIL: zero checks ran")
    sys.exit(1)
if fails:
    print("\n".join(f"FAIL {f}" for f in fails))
    sys.exit(1)
print(f"PASS: {examined} whisper render thumbnail check(s)")
