"""The disk guard deletes an upload only once YouTube says processed and its
Shorts are done - its master, its R2 copy and its spare copies together -
never re-renders what it pruned, and refuses to render below the floor.

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
        # no R2 copy left, but the local file predates its upload: the uploaded cut
        "r2-gone-older": dict(up=True, shorts=True, yt="processed", shelf=None, uploaded_at="2099-01-01T00:00:00Z"),
        "swap-pending": dict(up=True, shorts=True, yt="processed", shelf="same"),
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
            if c.get("uploaded_at"):
                row["uploaded_at"] = c["uploaded_at"]
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

    # spare copies (her 17 Nov 2026 ruling: once on YouTube, gone everywhere)
    sup = renders / "superseded-short"
    sup.mkdir()
    spares = {s: [renders / f"{s}-final.mp4.pre-footage-only", sup / f"{s}-final.pre-lengthen.mp4"]
              for s in ("proven", "not-uploaded", "no-shorts")}
    for fs in spares.values():
        for f in fs:
            f.write_bytes(b"spare" * 100)
    for r in RP.RECORDS:
        (renders / f"proven-final.mp4{r}").write_text("{}")
    (renders / "proven-final.mp4.work").mkdir()
    (renders / "proven-final.mp4.work" / "0001.mp4").write_bytes(b"w" * 10)
    # pruned before this rule: its R2 copy and spare copies are still around
    old = renders / "earlier-final.mp4"
    old.write_bytes(b"earlier master" * 1000)
    (plans / "earlier.json").write_text(json.dumps([{"text": "earlier"}]))
    bucket.put(old, r2.render_key("earlier"))
    same, why = bucket.same_as(old, r2.render_key("earlier"))
    (renders / "earlier-final.mp4.pruned.json").write_text(json.dumps(
        {"slug": "earlier", "bytes": old.stat().st_size, "r2_proof": why,
         "plan_sha256": RP._sha(plans / "earlier.json")}))
    old.unlink()
    (renders / "earlier-final.mp4.pre-footage-only").write_bytes(b"spare" * 100)
    led["published"].append({"slug": "earlier", "video_id": "vid-earlier", "shorts_block": ["a"]})
    statuses["vid-earlier"] = {"uploadStatus": "processed"}

    done, kept = RP.prune_uploaded(renders, led, bucket, yt, plans, swaps={"swap-pending"})
    gone = {r["slug"] for r in done}
    if gone != {"proven", "r2-gone-older", "earlier"}:
        fails.append(f"deleted {sorted(gone)}, wanted proven, r2-gone-older, earlier")
    for s in slugs:
        exists = (renders / f"{s}-final.mp4").exists()
        if (s in ("proven", "r2-gone-older")) == exists:
            fails.append(f"{s}: render {'still on disk' if exists else 'deleted'}")
    if bucket.head(r2.render_key("proven")) is not None:
        fails.append("proven: its R2 copy was kept after YouTube processed it and its Shorts were done")
    if bucket.head(r2.render_key("earlier")) is not None:
        fails.append("earlier: an episode pruned before the rule kept its R2 copy")
    for s in ("no-shorts", "swap-pending", "yt-uploading"):
        if bucket.head(r2.render_key(s)) is None:
            fails.append(f"{s}: R2 copy deleted before YouTube processed it / Shorts done / swap settled")
    if any(f.exists() for f in spares["proven"]) or (renders / "proven-final.mp4.work").exists() \
            or (renders / "earlier-final.mp4.pre-footage-only").exists():
        fails.append("spare copies of an uploaded episode were kept")
    if not all(f.exists() for s in ("not-uploaded", "no-shorts") for f in spares[s]):
        fails.append("spare copies of an episode not yet done on YouTube were deleted")
    if not all((renders / f"proven-final.mp4{r}").exists() for r in RP.RECORDS):
        fails.append("the master's own records were deleted with its spare copies")
    if not (renders / "earlier-final.mp4.pruned.json").exists():
        fails.append("the pruned marker was removed: the batch would re-render it")
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
    rc, line = RP.guard(6.0, renders, free=lambda: 2.0, led=led, bucket=bucket, yt=yt, plans=plans,
                        swaps=set())
    if rc != 3 or "NAMED STOP [DISK_LOW]" not in line:
        fails.append(f"2 GiB free under a 6 GiB floor gave rc={rc}: {line[:120]}")
    rc, line = RP.guard(6.0, renders, free=lambda: 40.0, led=led, bucket=bucket, yt=yt, plans=plans,
                        swaps=set())
    if rc != 0:
        fails.append(f"40 GiB free gave rc={rc}: {line[:120]}")

    # an unreachable YouTube deletes nothing and the floor still decides
    (renders / "yt-down-final.mp4").write_bytes(b"x" * 100)
    led["published"].append({"slug": "yt-down", "video_id": "v", "shorts_block": ["a"]})

    def down(ids):
        raise OSError("network down")

    rc, line = RP.guard(6.0, renders, free=lambda: 2.0, led=led, bucket=bucket, yt=down, plans=plans,
                        swaps=set())
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
