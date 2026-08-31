#!/usr/bin/env python3
"""Paste-ready metadata for a MANUAL YouTube Studio session.

Reuses loop/upload.py's build_payload rather than composing a second time. That
function derives every line from the script - direct answer, chapters, sources -
under the same no-invented-values rule the render pipeline enforces on screen.
A separate implementation here would be a second list with nothing linking it.
"""
import json, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "loop"))
import upload as up

order = json.loads((ROOT / "research/publish_order.json").read_text())
queue = order["queue"]
outdir = ROOT / "channel/upload"; outdir.mkdir(parents=True, exist_ok=True)

wrote = 0
for rec in queue[:4]:
    slug = rec["slug"]
    item = {"question": rec["query"], "script": f"scripts/{slug}.md"}
    p = up.build_payload(item)["snippet"]
    thumb = next((str(t.relative_to(ROOT)) for t in
                  (ROOT / "channel/thumbnails").glob(f"{slug.split('-')[0]}*")), "NOT FOUND")
    video = next((str(v.relative_to(ROOT)) for v in ROOT.glob(f"renders/{slug}*.mp4")
                  if "work" not in v.name), "NOT RENDERED YET")
    txt = f"""PUBLISH #{rec['queue_position']}  —  score {rec['combined_score']}

VIDEO FILE
{video}

THUMBNAIL
{thumb}

TITLE  ({len(p['title'])}/100)
{p['title']}

DESCRIPTION  ({len(p['description'])}/5000)
{'-'*66}
{p['description']}
{'-'*66}

TAGS
{', '.join(p['tags'])}

CATEGORY   Education
VISIBILITY see channel/upload/SESSION.md
"""
    (outdir / f"{rec['queue_position']}-{slug}.txt").write_text(txt)
    print(f"  {rec['queue_position']}. {slug[:44]:<44} title {len(p['title'])}ch  desc {len(p['description'])}ch  {len(p['tags'])} tags")
    wrote += 1

if wrote == 0:
    sys.exit("Rule 0: wrote no upload sheets")
print(f"\n  {wrote} sheets -> channel/upload/")
