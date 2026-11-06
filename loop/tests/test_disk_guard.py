"""The disk guard deletes ONLY uploads proven on YouTube and in R2, never
re-renders what it pruned, and refuses to render below the floor.

WHY (6 Nov 2026): the Mac's data disk reached 100% (1.8 GiB free) with
renders/ at 13 GiB, because no step ever removed a live render after its
upload. loop/render_prune.py `guard` now runs before every nightly render.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import r2  # noqa: E402
import render_prune as RP  # noqa: E402

fails = []

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    renders, plans, shelf = td / "renders", td / "plans", td / "shelf"
    renders.mkdir(); plans.mkdir()
    bucket = r2.LocalBackend(shelf)
    slugs = {
        "proven": dict(up=True, shorts=True, yt="processed", shelf="same"),
        "not-uploaded": dict(up=False, shorts=False, yt=None, shelf="same"),
        "no-shorts": dict(up=True, shorts=False, yt="processed", shelf="same"),
        "yt-missing": dict(up=True, shorts=True, yt=None, shelf="same"),
        "yt-uploading": dict(up=True, shorts=True, yt="uploaded", shelf="same"),
        "r2-differs": dict(up=True, shorts=True, yt="processed", shelf="other"),
        "r2-absent": dict(up=True, shorts=True, yt="processed", shelf=None),
    }
    led = {"published": []}
    statuses = {}
    for s, c in slugs.items():
        f = renders / f"{s}-final.mp4"
        f.write_bytes(f"master of {s}".encode() * 1000)
        (plans / f"{s}.json").write_text(json.dumps([{"text": s}]))
        if c["shelf"] == "same":
            bucket.put(f, r2.render_key(s))
        elif c["shelf"] == "other":
            o = td / f"{s}.other"
            o.write_bytes(b"a different cut" * 1000)
            bucket.put(o, r2.render_key(s))
        if c["up"]:
            row = {"slug": s, "video_id": f"vid-{s}", "privacy": "private"}
            if c["shorts"]:
                row["shorts_block"] = ["a", "b"]
            led["published"].append(row)
        if c["yt"]:
            statuses[f"vid-{s}"] = {"uploadStatus": c["yt"]}
    # a retired upload is not an upload
    led["published"].append({"slug": "not-uploaded", "video_id": "old", "retired_at": "x",
                             "shorts_block": ["a"]})

    asked = []

    def yt(ids):
        asked.append(list(ids))
        return {i: statuses[i] for i in ids if i in statuses}

    done, kept = RP.prune_uploaded(renders, led, bucket, yt, plans)
    gone = {r["slug"] for r in done}
    if gone != {"proven"}:
        fails.append(f"deleted {sorted(gone)}, wanted only ['proven']")
    for s in slugs:
        exists = (renders / f"{s}-final.mp4").exists()
        if (s == "proven") == exists:
            fails.append(f"{s}: render {'still on disk' if exists else 'deleted'}")
    if len(asked) != 1:
        fails.append(f"YouTube asked {len(asked)} times; one batched call expected")
    if not RP.pruned("proven", renders, plans):
        fails.append("pruned() does not see the marker: the batch would re-render it")
    if RP.pruned("not-uploaded", renders, plans):
        fails.append("pruned() is true for an episode that was never pruned")
    (plans / "proven.json").write_text(json.dumps([{"text": "a remake re-planned"}]))
    if RP.pruned("proven", renders, plans):
        fails.append("pruned() still true after the plan changed: a remake would never render")

    # the floor: below it after pruning is DISK_LOW, never a silent pass
    rc, line = RP.guard(6.0, renders, free=lambda: 2.0, led=led, bucket=bucket, yt=yt, plans=plans)
    if rc != 3 or "NAMED STOP [DISK_LOW]" not in line:
        fails.append(f"2 GiB free under a 6 GiB floor gave rc={rc}: {line[:120]}")
    rc, line = RP.guard(6.0, renders, free=lambda: 40.0, led=led, bucket=bucket, yt=yt, plans=plans)
    if rc != 0:
        fails.append(f"40 GiB free gave rc={rc}: {line[:120]}")

    # an unreachable YouTube deletes nothing and the floor still decides
    (renders / "yt-down-final.mp4").write_bytes(b"x" * 100)
    led["published"].append({"slug": "yt-down", "video_id": "v", "shorts_block": ["a"]})

    def down(ids):
        raise OSError("network down")

    rc, line = RP.guard(6.0, renders, free=lambda: 2.0, led=led, bucket=bucket, yt=down, plans=plans)
    if not (renders / "yt-down-final.mp4").exists() or rc != 3:
        fails.append("YouTube unreachable: a render was deleted or the floor was ignored")

# the batch honours the marker and the guard (the shell wiring)
sh = (Path(__file__).resolve().parents[2] / "bin" / "batch-session.sh").read_text()
for need in ("render_prune.pruned(slug)", "loop/render_prune.py is-pruned",
             "loop/render_prune.py guard", '"$GUARD_OUT"'):
    if need not in sh:
        fails.append(f"bin/batch-session.sh lost {need!r}")

if fails:
    print("FAIL test_disk_guard")
    for f in fails:
        print("  " + f)
    sys.exit(1)
print("ok test_disk_guard: only the proven upload deleted, no re-render, DISK_LOW below the floor")
