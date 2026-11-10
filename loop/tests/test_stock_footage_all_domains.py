"""Stock footage in every domain (owner, 2026-11-02: "Yes, all topics").

Pixabay / Mixkit (and Pexels once it has a key) moving footage may be placed in
deep-sea and materials episodes, on the food terms: commercial use, no
attribution required, licence wording stored and re-checked, credited on
screen. NOAA stays preferred wherever it matches. "A clip that doesn't show the
subject is worse than none."

  1. the licence gate clears a Pixabay and a Mixkit record, and REFUSES one
     that requires attribution, forbids commercial use, carries CC-BY or
     non-commercial wording, comes from Pexels with no wording, or names an
     unknown source
  2. NEGATIVE PROOF in a deep-sea episode (are-sea-pigs-real): a cleared stock
     clip is placed; the same clip marked attribution-required, then
     commercial-use-forbidden, is REFUSED by footage.usable_assets and by
     render_cut; restored, it is placed again
  3. the subject gate: "goblin shark" never takes a "shark" clip; a clip tagged
     "pig, farm, sea" is not a sea pig; a species beat never gets a stock clip
  4. NOAA preferred: an episode whose NOAA pool covers its ambient beats gets
     no stock clip; a materials episode gets stock and no NOAA
  5. Pexels with no key is the NAMED STOP PEXELS_KEY_ABSENT, not an error
  6. the weekly lane finds the harvester for both domains, with its gate
  7. visuals/assemble.py actually renders the stock clip as footage, exact frame count
     (needs ffmpeg; on a host without it this one check is a NOTE)

Hard-fails if it examines zero checks.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
sys.path.insert(0, LOOP)
sys.path.insert(0, os.path.join(ROOT, "visuals"))
sys.path.insert(0, os.path.join(ROOT, "research"))
os.environ["LOOP_DRY_RUN"] = "1"

import footage as FT  # noqa: E402
import imagery_stock_video as SV  # noqa: E402

fails: list[str] = []
examined = 0


def want(cond: bool, msg: str) -> None:
    global examined
    examined += 1
    if not cond:
        fails.append(msg)


def refusal_of(call) -> BaseException | None:
    """What `call` raised, or None when it returned. The caller asserts it is
    the refusal it expects, so a call that goes through is a named failure."""
    try:
        call()
    except Exception as e:                       # noqa: BLE001 - returned to the caller, which asserts its type
        return e
    return None


def stock(source: str, sid: str, tags: str, subject: str, local: str, blob: bytes) -> dict:
    lic = SV.LICENCES[source]
    wording = open(os.path.join(SV.IMAGERY, lic["licence_text"])).read()
    return {
        "post_id": f"{source}:{sid}", "source": source, "source_id": sid,
        "title": tags, "caption": f"{subject} - {tags}", "subject": subject,
        "source_org": "someone", "local_file": local, "width": 1920, "height": 1080,
        "seconds": 12.0, "clean_windows": [{"start": 0.0, "end": 12.0}],
        "treatment": "as-shot", "crop": None,
        "licence": lic["licence"], "licence_text": lic["licence_text"],
        "licence_wording": "\n".join(l for l in wording.splitlines()
                                     if any(g in l for g in lic["grants"])),
        "licence_basis": f"{lic['licence']}: API result for this id",
        "attribution_required": False, "commercial_use_permitted": True,
        "required_credit": f"FOOTAGE: SOMEONE / {source.upper()}",
        "sha256": hashlib.sha256(blob).hexdigest(),
    }


def noaa(pid: int, title: str, local: str, blob: bytes) -> dict:
    return {"post_id": pid, "title": title, "caption": title, "source_org": "NOAA Ocean Exploration",
            "local_file": local, "width": 1920, "height": 1080, "seconds": 30.0,
            "clean_windows": [{"start": 2.0, "end": 28.0}], "treatment": "as-shot",
            "crop": None, "commercial_use_permitted": True,
            "required_credit": "NOAA Ocean Exploration",
            "sha256": hashlib.sha256(blob).hexdigest()}


def ambient(n: int, seconds: float = 3.0) -> list[dict]:
    return [{"segment": "ambient_drift", "seconds": seconds, "args": {"variant": i % 5},
             "narration": "x"} for i in range(n)]


class fixture:
    """A temp imagery dir + manifest that footage.py reads instead of the Mac's."""

    def __init__(self, assets: list[dict], blobs: dict[str, bytes]):
        self.assets, self.blobs = assets, blobs

    def __enter__(self):
        self.dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.dir, "clips"))
        for rel, b in self.blobs.items():
            open(os.path.join(self.dir, rel), "wb").write(b)
        self.man = os.path.join(self.dir, "video_rights.json")
        json.dump({"assets": self.assets}, open(self.man, "w"))
        self.old = (FT.MANIFEST, FT.IMAGERY_DIR, dict(FT._VERIFIED))
        FT.MANIFEST, FT.IMAGERY_DIR = self.man, self.dir
        FT._VERIFIED.clear()
        return self

    def write(self, assets):
        json.dump({"assets": assets}, open(self.man, "w"))
        FT._VERIFIED.clear()

    def __exit__(self, *a):
        FT.MANIFEST, FT.IMAGERY_DIR, cache = self.old
        FT._VERIFIED.clear()
        FT._VERIFIED.update(cache)
        shutil.rmtree(self.dir, ignore_errors=True)


def refused(assets) -> str | None:
    try:
        FT.usable_assets({"assets": assets})
        return None
    except FT.RightsRefusal as e:
        return str(e)


def main() -> int:
    blob_a, blob_b, blob_n = b"sea-pig-bytes", b"glass-bytes", b"noaa-bytes"
    pig = stock("pixabay", "101", "sea pig, sea cucumber, seafloor", "sea pig",
                "clips/stock__pixabay-101.mp4", blob_a)
    glass = stock("mixkit", "202", "molten glass being shaped", "glass",
                  "clips/stock__mixkit-202.mp4", blob_b)

    # -- 1. the licence gate ----------------------------------------------
    for rec in (pig, glass):
        ok, why = SV.stock_licence_ok(rec)
        want(ok, f"a clean {rec['source']} record was refused: {why}")
    for label, mut in [
        ("attribution required", lambda r: r.update(attribution_required=True)),
        ("attribution not recorded", lambda r: r.pop("attribution_required")),
        ("commercial use forbidden", lambda r: r.update(commercial_use_permitted=False)),
        ("CC-BY wording", lambda r: r.update(licence_wording=r["licence_wording"] + "\nCC BY 4.0")),
        ("non-commercial wording", lambda r: r.update(licence_basis="Non-commercial use only")),
        ("licence wording missing", lambda r: r.update(licence_wording="")),
        ("wrong licence name", lambda r: r.update(licence="Some Other License")),
        ("Pexels with no wording", lambda r: r.update(source="pexels", licence="Pexels License")),
        ("unknown source", lambda r: r.update(source="shutterstock")),
    ]:
        r = copy.deepcopy(pig)
        mut(r)
        ok, _ = SV.stock_licence_ok(r)
        want(not ok, f"the licence gate CLEARED a record with {label}")

    # -- 2. negative proof in a deep-sea episode ----------------------------
    slug = "are-sea-pigs-real"
    want(FT.episode_domain(slug) == "deep-sea-ocean-science",
         f"{slug} is not read as a deep-sea episode")
    blobs = {pig["local_file"]: blob_a}
    with fixture([pig], blobs) as fx:
        cuts = FT.assign(ambient(2), [3.0, 3.0], slug)
        want(sum(1 for c in cuts if c) == 2 and all(
             c["asset"]["post_id"] == "pixabay:101" for c in cuts if c),
             f"a cleared sea-pig clip was not placed on {slug}'s ambient beats: {cuts}")
        want(all(c["credit"] == "FOOTAGE: SOMEONE / PIXABAY" for c in cuts if c),
             "a placed stock clip is not credited on screen")
        for label, mut in [("attribution required", {"attribution_required": True}),
                           ("commercial use forbidden", {"commercial_use_permitted": False})]:
            bad = {**pig, **mut}
            fx.write([bad])
            why = refused([bad])
            want(why is not None and "stock licence refused" in why,
                 f"footage.usable_assets did not refuse a clip with {label} in {slug}")
            raised = refusal_of(lambda: FT.assign(ambient(2), [3.0, 3.0], slug))
            want(isinstance(raised, FT.RightsRefusal),
                 f"footage.assign did not refuse a manifest holding a clip with "
                 f"{label} in {slug} (raised {type(raised).__name__})")
            raised = refusal_of(lambda: FT.render_cut(
                {**cuts[0], "asset": bad}, os.devnull, 3.0, fx.dir))
            want(isinstance(raised, FT.RightsRefusal),
                 f"render_cut did not stop at the licence gate for a clip with "
                 f"{label} (raised {type(raised).__name__})")
        fx.write([pig])
        want(refused([pig]) is None, "the restored clip is still refused")
        want(sum(1 for c in FT.assign(ambient(2), [3.0, 3.0], slug) if c) == 2,
             "the restored clip is not placed again")

    # -- 3. the subject gate --------------------------------------------------
    # Exercise the slug fallback with no shot list; live batch lists now
    # contain narrower shots and scientific names for this episode.
    with patch.object(SV, "_shot_list", return_value=[]):
        want(SV.episode_phrases("what-does-a-goblin-shark-look-like") == ["goblin shark"],
             "the slug fallback lost the specific goblin shark subject")
    want(SV.episode_phrases("why-deep-sea-creatures-are-surfacing") == [],
         "an episode named only by generic ocean words (and no shot list) still asks "
         "for stock footage")
    want(not SV.phrase_in("goblin shark", "shark, ocean, fish"),
         "a plain shark clip matched 'goblin shark'")
    want(not SV.phrase_in("sea pig", "pig, farm, sea"),
         "a farm pig by the sea matched 'sea pig'")
    want(SV.phrase_in("sea pig", "sea pigs, seafloor, echinoderm"),
         "a clip whose first tag is 'sea pigs' did not match 'sea pig'")
    # the clips a looser rule actually accepted on the 2026-11-02 live run
    for phrase, title in [("diamond", "bird, diamond pigeon, pigeon species"),
                          ("diamond", "a diamond engagement ring"),
                          ("diamond", "multicolor diamond lights"),
                          ("whale", "dolphin, whale, shark, pool"),
                          ("metal", "heavy metal, rock band, music"),
                          ("glass", "glass maker, glass blower, molten"),
                          ("steel", "river, bridge, steel, railway"),
                          ("sea pig", "seafloor, sea pigs, echinoderm")]:
        want(not SV.phrase_in(phrase, title),
             f"{title!r} was taken as showing {phrase!r}")
    want(SV.phrase_in("glass", "molten glass being shaped"),
         "a Mixkit title whose head noun is the subject was refused")
    # the SLUG fallback (no shot list): these episodes now carry shot lists
    # (visuals/shot_list.py, PICTURE FIRST 3 Nov 2026) whose filmable subjects
    # rightly win, so the slug-word rule is proven with the shot list absent
    with patch.object(SV, "_shot_list", return_value=[]):
        for other in ("05-why-many-deep-sea-creatures-are-red",
                      "19-what-is-the-deepest-fish-ever-recorded",
                      "10-what-is-the-deepest-part-of-the-ocean"):
            want(SV.episode_phrases(other) == [],
                 f"{other} asks stock for {SV.episode_phrases(other)} - an adjective "
                 f"or verb is not a subject a clip can show")
    farm = stock("pixabay", "303", "pig, farm, sea", "sea pig", "clips/stock__pixabay-303.mp4", b"farm")
    want(FT.stock_pool(slug, [farm]) == [], "a farm-pig clip entered the sea-pig pool")
    octo = stock("pixabay", "404", "octopus, dumbo octopus", "dumbo octopus",
                 "clips/stock__pixabay-404.mp4", b"o")
    want(FT.subject_pool("deep_octopus", [octo]) == [],
         "a species beat took a stock clip - a species label is NOAA-only")

    # -- 4. NOAA preferred; materials gets stock --------------------------------
    red = "05-why-many-deep-sea-creatures-are-red"
    reds = [noaa(i, t, f"clips/n{i}.mp4", blob_n) for i, t in
            enumerate(["Red Shrimp", "Big Red Jelly", "Red Jelly"])]
    red_stock = stock("pixabay", "505", "red shrimp, sea", "red shrimp", "clips/stock__pixabay-505.mp4", b"r")
    pool = FT.episode_pool(red, reds + [red_stock], needed=2)
    want(pool and all(not SV.is_stock(a) for a in pool),
         f"a stock clip entered {red}'s pool while NOAA covers it")
    gl = "why-is-glass-clear"
    want(FT.episode_domain(gl) == "materials-and-manufacturing", f"{gl} is not materials")
    pool = FT.episode_pool(gl, reds + [glass], needed=2)
    want([a["post_id"] for a in pool] == ["mixkit:202"],
         f"{gl} pool is {[a['post_id'] for a in pool]}, wanted the glass clip only")

    # -- 5. Pexels: named stop ------------------------------------------------
    old = {k: os.environ.get(k) for k in ("HWK_FOOTAGE_KEY_DIR", "PEXELS_API_KEY")}
    os.environ["HWK_FOOTAGE_KEY_DIR"] = tempfile.mkdtemp()
    os.environ.pop("PEXELS_API_KEY", None)
    try:
        status, stops = SV.source_status()
        want([s["code"] for s in stops] == ["PEXELS_KEY_ABSENT"],
             f"Pexels with no key is not the named stop PEXELS_KEY_ABSENT: {stops}")
        want(status["mixkit"] == "usable", f"Mixkit not usable without keys: {status}")
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # -- 6. the lane finds it ---------------------------------------------------
    import footage_lane as FL  # noqa: E402
    hs = [h for h in FL.declared_harvesters() if h["rel"] == "research/imagery_stock_video.py"]
    want(len(hs) == 1 and set(hs[0]["domains"]) >= {"deep-sea-ocean-science",
                                                     "materials-and-manufacturing"},
         "the stock harvester is not declared for deep sea and materials")
    if hs:
        try:
            FL.assert_rights_gate(hs[0]["rel"], hs[0]["gate"])
            want(True, "")
        except FL.RightsGateMissing as e:
            want(False, f"the lane refuses the stock harvester: {e}")
        cfg = {"domains": {"allocation": {"materials-and-manufacturing": 2}}}
        picked, uncovered = FL.harvesters_for(cfg)
        want(any(h["rel"] == hs[0]["rel"] for h in picked) and not uncovered,
             "a materials-only allocation does not pick the stock harvester")

    # -- 7. assemble.py renders a footage beat ------------------------------------
    if not shutil.which("ffmpeg"):
        print("  NOTE  no ffmpeg on this host: assemble.py's footage render was not "
              "exercised here; it runs on the Mac, which renders every episode.")
    else:
        import assemble as ASM  # noqa: E402
        tmp = tempfile.mkdtemp()
        try:
            src = os.path.join(tmp, "src.mp4")
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                            "-i", "testsrc=size=640x360:rate=30:duration=12", "-c:v", "libx264",
                            "-preset", "ultrafast", "-pix_fmt", "yuv420p", src], check=True)
            blob = open(src, "rb").read()
            rec = {**pig, "local_file": "clips/stock__pixabay-101.mp4",
                   "sha256": hashlib.sha256(blob).hexdigest()}
            with fixture([rec], {rec["local_file"]: blob}):
                plan = os.path.join(tmp, f"{slug}.json")
                json.dump(ambient(1, 2.5), open(plan, "w"))
                out = os.path.join(tmp, "out.mp4")
                os.environ["HWK_MIN_FREE_GB"] = "0"   # not the CI disk's business
                r = ASM.assemble(plan, out, music=False, frame_check=False)
                want(r["footage"]["footage_shots"] >= 1 and r["footage"]["photo_shots"] == 0,
                     f"assemble.py put no stock footage on screen: {r.get('footage')}")
                n = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                    "-count_packets", "-show_entries",
                                    "stream=nb_read_packets", "-of", "default=nw=1:nk=1",
                                    out], capture_output=True, text=True).stdout.strip()
                import math
                want(n == str(math.ceil(2.5 * FT.FPS)),
                     f"the footage render has {n} frames, wanted {math.ceil(2.5 * FT.FPS)}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    if examined == 0:
        print("FAIL: examined zero checks")
        return 1
    for f in fails:
        print("FAIL:", f)
    print(f"{examined} check(s), {len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
