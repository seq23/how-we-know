"""A Short that fails V14/V15 holds THAT Short - never its siblings, never an episode.

From 2026-10-08 the Mac's nightly push ended NAMED STOP [SHORTS_UNVERIFIED]
every night: two deep-sea cuts failed V14 and one failed V15, and
loop/r2.py:push_shorts gated the WHOLE `shorts/` directory, so not one of the
81 cut Shorts was shelved and no Short posted while Shorts carry most of the
channel's views. A guard must not reach beyond what it governs.

Proves, with no network, no Vision and no credential (validators faked at the
loop/validate.py boundary, so r2.verify_shorts' own logic is what is tested):

  1. a failing cut, named by the validator, is NOT shelved, and is reported in
     the result's `held` list;
  2. every other cut - including the failing cut's own sibling ranks - and its
     receipt IS shelved;
  3. the episode push (r2.push) shelves renders and thumbnails while the Shorts
     validators are failing - it never consults them;
  4. a failure that names no cut (validator crashed / examined nothing) still
     refuses the whole shelf with SHORTS_UNVERIFIED - no cut ships unproven;
  5. V14 and V15 pin their per-Short failures to the file (Result.fail_file),
     so the hold above can actually reach them.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

LOOP = Path(__file__).resolve().parents[1]
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))
os.environ.setdefault("LOOP_DRY_RUN", "1")

tmp = Path(tempfile.mkdtemp(prefix="shorts-gate-per-cut-"))
os.environ["LOOP_RENDER_HOLD"] = str(tmp / "render_hold.json")
os.environ["LOOP_STOPS_DIR"] = str(tmp / "stops")

import domains  # noqa: E402
import r2 as R  # noqa: E402
import shorts_lane as SL  # noqa: E402
import validate as V  # noqa: E402

fails: list[str] = []
examined = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global examined
    examined += 1
    if not ok:
        fails.append(f"{name}: {detail}")


by = domains.by_slug()
deep = sorted(s for s, d in by.items() if d == "deep-sea-ocean-science")
assert len(deep) >= 2, "need two real deep-sea slugs"
a, b = deep[0], deep[1]

repo = tmp / "repo"
(repo / "shorts").mkdir(parents=True)
(repo / "renders").mkdir()
(repo / "channel" / "thumbnails").mkdir(parents=True)
cuts = []
for s in (a, b):
    for r in range(1, SL.cuts_for(s) + 1):
        f = repo / "shorts" / SL.short_file(s, r)
        f.write_bytes(os.urandom(64))
        Path(f"{f}.short.json").write_text(json.dumps({"ok": True}))
        cuts.append((s, r))
    (repo / "renders" / f"{s}-final.mp4").write_bytes(os.urandom(128))
    (repo / "channel" / "thumbnails" / f"{s}.jpg").write_bytes(os.urandom(32))
check("0 fixture has at least three cuts", len(cuts) >= 3, str(cuts))

bad = SL.short_file(a, 2 if SL.cuts_for(a) >= 2 else 1)


def fake(name, failures, files):
    r = V.Result(name)
    r.examined = 3
    for f in failures:
        if f.split(":")[0] in files:
            r.fail_file(f.split(":")[0], f)
        else:
            r.fail(f)
    return lambda: r


R.ROOT = repo
_dry = os.environ.pop("LOOP_DRY_RUN", None)
try:
    # ---- 1 + 2: a named failing cut holds only itself -----------------------
    V.v14_shorts_attribution = fake(
        "V14 shorts-attribution",
        [f"{bad}: credit 'NOAA Ocean Exploration' is not on screen"], {bad})
    V.v15_shorts_caption_crop = fake("V15 shorts-caption-crop", [], set())
    shelf = R.LocalBackend(tmp / "shelf")
    try:
        res = R.push_shorts(shelf, [a, b])
        refused_all = None
    except R.R2Unavailable as e:
        res, refused_all = {}, e.code
    check("1 one bad cut did not refuse the whole shelf", refused_all is None,
          f"raised {refused_all}")
    bad_rank = 2 if bad.endswith("-short2.mp4") else 1
    check("1 the failing cut is NOT shelved",
          not shelf.head(R.short_key(a, bad_rank))
          and not shelf.head(R.short_receipt_key(a, bad_rank)), bad)
    check("1 the failing cut is named in `held`",
          any(SL.Pick(a, bad_rank).label in h for h in res.get("held", [])),
          str(res.get("held")))
    others = [(s, r) for s, r in cuts if not (s == a and r == bad_rank)]
    missing = [(s, r) for s, r in others
               if not (shelf.head(R.short_key(s, r))
                       and shelf.head(R.short_receipt_key(s, r)))]
    check("2 every other cut and receipt IS shelved", not missing and others,
          f"missing {missing}")

    # ---- 3: episodes never wait on the Shorts validators -------------------
    def boom():
        raise AssertionError("episode push consulted the Shorts validators")
    R.verify_shorts = boom
    eshelf = R.LocalBackend(tmp / "eshelf")
    try:
        er = R.push(eshelf, [a, b])
        err = None
    except AssertionError as e:
        er, err = {}, str(e)
    check("3 episode push never consults V14/V15", err is None, str(err))
    check("3 episode renders and thumbnails shelved while Shorts fail",
          all(eshelf.head(R.render_key(s)) and eshelf.head(R.thumb_key(s))
              for s in (a, b)), str(er))
    del R.verify_shorts
    import importlib
    importlib.reload(R)
    R.ROOT = repo

    # ---- 4: an unattributable failure still holds everything ---------------
    V.v14_shorts_attribution = fake(
        "V14 shorts-attribution",
        ["examined 0 Shorts that carry credited material"], set())
    V.v15_shorts_caption_crop = fake("V15 shorts-caption-crop", [], set())
    shelf4 = R.LocalBackend(tmp / "shelf4")
    try:
        R.push_shorts(shelf4, [a, b])
        code = None
    except R.R2Unavailable as e:
        code = e.code
    check("4 a failure naming no cut refuses the whole shelf",
          code == "SHORTS_UNVERIFIED", str(code))
    check("4 and nothing was shelved",
          not any(shelf4.head(R.short_key(s, r)) for s, r in cuts))
finally:
    if _dry is not None:
        os.environ["LOOP_DRY_RUN"] = _dry

# ---- 5: the real validators pin per-Short failures to the file ------------
src = (LOOP / "validate.py").read_text()
for fn in ("def v14_shorts_attribution", "def v15_shorts_caption_crop"):
    body = src[src.find(fn):]
    body = body[:body.find("\ndef ", 10)]
    per_short = body.count("r.fail(f\"{mp4.name}") + body.count("r.fail(f'{mp4.name}")
    check(f"5 {fn[4:]} pins every per-Short failure to its file",
          "r.fail_file(mp4.name" in body and per_short == 0,
          f"{per_short} per-Short failure(s) still unpinned")

if examined == 0:
    print("FAIL test_shorts_gate_holds_only_the_cut: examined nothing")
    sys.exit(1)
if fails:
    print("FAIL test_shorts_gate_holds_only_the_cut:")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print(f"OK  test_shorts_gate_holds_only_the_cut: {examined} checks - a failing "
      f"cut holds only itself, its siblings and every episode ship, an "
      f"unattributable failure still holds the shelf")
