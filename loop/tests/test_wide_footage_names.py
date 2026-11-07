"""Wide footage clips get unique names with their real extension, and a
collided clip is re-homed only when its bytes still match its rights record.

2026-11-06: two Commons clips whose ids share their first 60 characters were
saved to ONE file (`...-can.org&`); the second overwrote the first, its sha256
no longer matched, and visuals/footage.usable_assets() refused every clip -
no render could run on the Mac.
"""
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research"))
import wide_footage as WF  # noqa: E402

fails = []
URL = "https://upload.wikimedia.org/x/Kiska.webm?utm_source=commons.wikimedia.org&utm_content=original"
a_id = "Kiska Orcinus orca killer whale Marineland Niagara Falls Canada 2022-08-15 2.06.16PM.webm"
b_id = "Kiska Orcinus orca killer whale Marineland Niagara Falls Canada 2022-08-15 2.09.40PM.webm"
na, nb = WF.clip_name("commons", a_id, URL), WF.clip_name("commons", b_id, URL)
if na == nb:
    fails.append(f"two clips share a name: {na}")
if not na.endswith(".webm") or "&" in na:
    fails.append(f"extension not taken from the URL path: {na}")

with tempfile.TemporaryDirectory() as td:
    clips = Path(td) / "clips"
    clips.mkdir()
    blob_a, blob_b = b"A" * 100, b"B" * 70
    shared = "clips/wide__commons__kiska-orcinus-orca-killer-whale-marineland-niagara-falls-can.org&"
    (Path(td) / shared).write_bytes(blob_b)                 # b overwrote a
    man = {"assets": [
        {"post_id": f"commons:{a_id}", "local_file": shared, "direct_url": "u-a",
         "sha256": hashlib.sha256(blob_a).hexdigest(), "bytes": len(blob_a)},
        {"post_id": f"commons:{b_id}", "local_file": shared, "direct_url": "u-b",
         "sha256": hashlib.sha256(blob_b).hexdigest(), "bytes": len(blob_b)},
        {"post_id": "commons:gone", "local_file": "clips/wide__commons__gone.org&", "direct_url": "u-c",
         "sha256": hashlib.sha256(b"C").hexdigest(), "bytes": 1},
        {"post_id": "noaa:1", "local_file": "clips/1__noaa.mp4", "direct_url": "n", "sha256": "x", "bytes": 5},
    ]}
    served = {"u-a": blob_a, "u-b": blob_b, "u-c": b"CHANGED"}
    r = WF.repair(man, download=lambda u: served[u], clips=str(clips))
    files = [a["local_file"] for a in man["assets"]]
    if r != {"fixed": 2, "dropped": 1}:
        fails.append(f"repair result {r}, wanted 2 fixed and 1 dropped")
    if len(set(files)) != len(files):
        fails.append(f"two assets still share a file: {files}")
    for a in man["assets"]:
        p = Path(td) / a["local_file"]
        if a["post_id"].startswith("commons:") and hashlib.sha256(p.read_bytes()).hexdigest() != a["sha256"]:
            fails.append(f"{a['post_id'][:30]}: kept with bytes that differ from its rights record")
    if any(a["post_id"] == "commons:gone" for a in man["assets"]):
        fails.append("a clip whose bytes changed was kept instead of dropped")
    if not any(a["post_id"] == "noaa:1" for a in man["assets"]):
        fails.append("a NOAA clip the repair does not govern was removed")

if fails:
    print("FAIL test_wide_footage_names")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("ok test_wide_footage_names: unique names, real extensions, repair keeps only verified bytes")
