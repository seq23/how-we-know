"""Description chapter times are the RENDER's, computed, never a stale cache.

On 14 Oct 2026 episode 20's live description put "How the zone connects the
surface and abyss" at 5:02 (the script's hand-written estimate) while the
render has it at 5:16 (316 s - the instant its rank-2 Short was cut from), and
captions/20-...chapters.txt, which loop/upload.py:build_chapters trusted
first, said 4:32: it was computed on 4 Sep from word-count ESTIMATES and never
recomputed. Three extended episodes' files predated the tail chapters they
added. 18 of 41 live descriptions carried drifted or invalid chapter lists.
Proves, with no network and no credential:

  1. build_chapters takes measured_chapters() first - a stale chapters.txt
     cannot win while measured timing exists;
  2. episode 20's chapters put the zone chapter at 5:16, from the measured
     durations (wavs on the Mac, audio/<slug>/beats.json in the cloud);
  3. for EVERY episode with a frozen plan and fully measured timing:
     build_chapters == measured_chapters, starts at 0:00, every chapter
     >= 10 s, and captions/<slug>.chapters.txt says the same thing (a cache
     that drifts from the render is a failure, not a fallback);
  4. an unmeasured episode still falls back (chapters.txt, then the script).

Hard-fails if it examines zero cases.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "loop"))
import upload as up                                        # noqa: E402

fails: list[str] = []
examined = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global examined
    examined += 1
    if not ok:
        fails.append(f"{name}" + (f": {detail}" if detail else ""))


CAP = up._visuals_captions()
check("0 visuals/captions.py is the module loaded, not the captions/ dir",
      bool(getattr(CAP, "__file__", "")) and CAP.__file__.endswith("visuals/captions.py"))

# ---- 1: measured first -----------------------------------------------------
saved = up.measured_chapters
try:
    up.measured_chapters = lambda slug: [(0, "Sentinel A"), (40, "Sentinel B"),
                                         (90, "Sentinel C")]
    got = up.build_chapters("20-what-is-the-midnight-zone", "")
    check("1 build_chapters takes measured_chapters first",
          got == ["0:00 Sentinel A", "0:40 Sentinel B", "1:30 Sentinel C"], str(got))
    up.measured_chapters = lambda slug: None
    script = "## Chapters\n\n- 00:00 Cold open\n- 00:12 Title card\n- 00:14 First\n- 01:00 Second\n\n## Sources\n"
    got = up.build_chapters("no-such-episode-anywhere", script)
    check("4 an unmeasured episode falls back to the script",
          got == ["0:00 Cold open", "0:14 First", "1:00 Second"], str(got))
finally:
    up.measured_chapters = saved

# ---- 2: episode 20 ----------------------------------------------------------
m20 = up.measured_chapters("20-what-is-the-midnight-zone")
if m20 is None:
    print("  · episode 20's timing is not measured here; part 2 skipped")
else:
    zone = [t for t, h in m20 if h == "How the zone connects the surface and abyss"]
    check("2 episode 20: the zone chapter is at 5:16 (316 s), as rendered",
          zone == [316], str(zone))
    check("2 episode 20's build_chapters says 5:16",
          "5:16 How the zone connects the surface and abyss"
          in up.build_chapters("20-what-is-the-midnight-zone", ""))

# ---- 3: every measured episode ---------------------------------------------
n = 0
for pj in sorted((ROOT / "plans").glob("*.json")):
    slug = pj.stem
    m = up.measured_chapters(slug)
    if not m:
        continue
    n += 1
    want = [f"{CAP.hms(t)} {h}" for t, h in m]
    got = up.build_chapters(slug, "")
    check(f"3 {slug}: build_chapters is the measured list", got == want)
    check(f"3 {slug}: starts at 0:00 and every chapter runs >= 10 s",
          m[0][0] == 0 and all(b[0] - a[0] >= 10 for a, b in zip(m, m[1:])))
    txt = ROOT / "captions" / f"{slug}.chapters.txt"
    cached = [l.strip() for l in txt.read_text().splitlines() if l.strip()] \
        if txt.exists() else None
    check(f"3 {slug}: captions/{slug}.chapters.txt agrees with the render",
          cached == want, f"cached {cached and cached[:3]} vs {want[:3]}")
check("3 examined at least one measured episode", n > 0)

if examined == 0:
    print("FAIL test_chapters_from_render: examined nothing")
    sys.exit(1)
if fails:
    print("FAIL test_chapters_from_render:")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print(f"OK  test_chapters_from_render: {examined} checks over {n} measured "
      f"episode(s) - description chapters are the render's")
