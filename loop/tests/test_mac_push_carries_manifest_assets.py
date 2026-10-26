"""A Mac lane that commits a rights manifest commits the files it names.

CONFIRMED on main, 2026-10-26 (loop · tests run 40287..., long-suite shard 1).
V30 rule B went FAIL(2):

    channel/imagery/food_ai.json is tracked and names
    assets/food_ai__chili-cross-macro__s7.jpg, which is not.

The food night of 2026-10-25 generated two stills on Workers AI, wrote them to
channel/imagery/assets/, recorded both in the manifest with their sha256 — and
then committed `channel/imagery/food_clips.json channel/imagery/food_ai.json`
and nothing else (bin/food-session.sh). mac_sync.push commits EXACTLY the paths
it is given and never `git add -A`, by design, so the manifest went to main and
the two JPEGs stayed on the Mac. Main went red, and would have gone red again
on the next food night that drew a new still.

V30 is the right guard and it is late: it fires on main, after the push, and
the asset it names is on a machine nobody is looking at. This test is the other
half, and it is static — it reads each Mac lane's push list out of bin/*.sh and
asks whether that list could carry the assets of every manifest in it.

THE RULE, and why it is not simply "commit the assets":
  channel/imagery/food_clips.json is tracked ON PURPOSE with its clips under the
  gitignored channel/imagery/clips/ — hundreds of megabytes that belong on the
  Mac and in R2, honest because every row pins a sha256. So the question is
  never "is this asset in git", it is V30's own question: an asset git IGNORES
  is machine-local by design; an asset git does NOT ignore must travel with its
  manifest. This test asks exactly that, of the push list rather than of main.

WHAT THIS PROVES:
  1. every `mac_sync.py push` list in bin/*.sh is found and parsed (hard-fails
     on zero lanes, so the test cannot pass by finding nothing);
  2. for every rights manifest in such a list, each asset it names that git does
     NOT ignore is covered by some path in the SAME list;
  3. NEGATIVE PROOF: with channel/imagery/assets removed from the food lane's
     list, the rule reports the food_ai.json defect — the one that redded main.
Hard-fails if it examines zero manifests.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
BIN = ROOT / "bin"

fails: list[str] = []
examined = 0

# A rights manifest names its files in one of these fields, relative to its own
# directory (channel/imagery/food_ai.json -> assets/x.jpg).
FILE_FIELDS = ("local_file", "file", "path", "asset")


def ignored(rel: str) -> bool:
    """git's own answer, never a guess about .gitignore's wording."""
    return subprocess.run(["git", "check-ignore", "-q", "--", rel],
                          cwd=ROOT).returncode == 0


def push_lists() -> dict[str, list[str]]:
    """Each lane's commit pathspecs, as bin/*.sh actually assembles them.

    Two shapes are in use: the paths inline on the `push --lane X a b c` line,
    and a PATHS variable built up over several lines and word-split into it.
    """
    lanes: dict[str, list[str]] = {}
    for script in sorted(BIN.glob("*.sh")):
        text = script.read_text()
        # PATHS="..." and PATHS="$PATHS ..." accumulated anywhere in the file.
        accumulated: list[str] = []
        for assign in re.finditer(r'^\s*PATHS="([^"]*)"', text, re.M):
            accumulated += [w for w in assign.group(1).split()
                            if not w.startswith("$")]
        for call in re.finditer(
                r"mac_sync\.py push --lane ([\w-]+)((?:[^\n]|\\\n)*)", text):
            lane, rest = call.group(1), call.group(2)
            inline = [w for w in rest.replace("\\\n", " ").split()
                      if w.endswith((".json", ".npz", ".srt", ".txt"))
                      or "/" in w and not w.startswith(("$", "-", "2>&1", "|"))]
            paths = [p for p in inline if not p.startswith("$")]
            if "$PATHS" in rest:
                paths += accumulated
            lanes.setdefault(f"{script.name}:{lane}", []).extend(paths)
    return lanes


def covered(asset_rel: str, paths: list[str]) -> bool:
    """Would committing `paths` carry this asset? A directory carries its tree."""
    a = Path(asset_rel)
    return any(a == Path(p) or Path(p) in a.parents for p in paths)


def audit(lanes: dict[str, list[str]]) -> tuple[list[str], int]:
    problems: list[str] = []
    seen = 0
    for lane, paths in lanes.items():
        for path in paths:
            if not path.endswith(".json"):
                continue
            manifest = ROOT / path
            if not manifest.exists():
                continue
            try:
                data = json.loads(manifest.read_text())
            except (ValueError, UnicodeDecodeError):
                continue
            rows = data.get("index") if isinstance(data, dict) else data
            if not isinstance(rows, list):
                continue
            named = [row[f] for row in rows if isinstance(row, dict)
                     for f in FILE_FIELDS
                     if isinstance(row.get(f), str) and "/" in row[f]]
            if not named:
                continue
            seen += 1
            for rel in sorted(set(named)):
                asset = f"{Path(path).parent}/{rel}"
                if ignored(asset):
                    continue  # machine-local by design, pinned by sha256
                if not covered(asset, paths):
                    problems.append(
                        f"{lane} commits {path} but no path in its list carries "
                        f"{asset}, which git does not ignore: the manifest "
                        f"would reach main without its file (V30 rule B)")
    return problems, seen


# ------------------------------------------------------------ 1. lanes parsed
lanes = push_lists()
examined += 1
if not lanes:
    fails.append("no `mac_sync.py push` lane was found in bin/*.sh, so this "
                 "test would pass by examining nothing")
food = [k for k in lanes if k.startswith("food-session.sh")]
examined += 1
if not food:
    fails.append("the food lane's push list was not found, and it is the lane "
                 "whose missing assets redded main on 2026-10-26")

# ------------------------------------------------- 2. the rule, on the real repo
problems, seen = audit(lanes)
examined += seen
if seen == 0:
    fails.append("no rights manifest with named files was found in any push "
                 "list, so the rule examined nothing")
for p in problems:
    fails.append(p)

# ------------------------------------------------------------ 3. negative proof
if food:
    broken = {k: [p for p in v if p != "channel/imagery/assets"]
              if k in food else v for k, v in lanes.items()}
    examined += 1
    back, _ = audit(broken)
    if not any("food_ai.json" in p for p in back):
        fails.append("NEGATIVE PROOF FAILED: with channel/imagery/assets taken "
                     "out of the food lane's list, the rule did not report the "
                     "food_ai.json defect that redded main")

if examined == 0:
    fails.append("examined nothing")
print(f"examined {len(lanes)} lane push list(s) and {seen} manifest(s) "
      f"({examined} case(s))")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
