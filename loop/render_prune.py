"""Keep at most ONE superseded copy of each episode's render.

A long-form master is ~550 MB. Every re-render moves the previous one aside
(never deleted: `.picture-check-failed`, `.below-picture-floor`,
`.pre-...`, `.incomplete...`), and on 2026-11-03 four aside copies of one
episode sat in renders/ while the Mac ran out of memory and disk. This keeps
the newest aside copy per episode and moves the older ones to the Trash
(~/.Trash on the Mac - recoverable, not deleted). The live render and its
`.footage.json` / `.render.json` records are never touched.

    .venv/bin/python loop/render_prune.py [--dry-run]
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RENDERS = ROOT / "renders"
TRASH = Path.home() / ".Trash"
KEEP = 1
RECORDS = (".footage.json", ".render.json")
ASIDE = re.compile(r"^(?P<slug>.+)-final\.mp4\.(?P<tag>[^/]+)$")


def aside_copies(renders: Path = RENDERS) -> dict[str, list[Path]]:
    """{slug: [aside master copies, newest first]} - records excluded."""
    out: dict[str, list[Path]] = {}
    for p in renders.iterdir() if renders.exists() else []:
        m = ASIDE.match(p.name)
        if not m or not p.is_file() or p.name.endswith(RECORDS):
            continue
        out.setdefault(m.group("slug"), []).append(p)
    for v in out.values():
        v.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return out


def prune(renders: Path = RENDERS, trash: Path = TRASH, keep: int = KEEP,
          dry_run: bool = False) -> list[Path]:
    """Move every aside copy past the newest `keep` (and its records) to `trash`."""
    moved = []
    for slug, copies in aside_copies(renders).items():
        for p in copies[keep:]:
            for q in [p] + [Path(str(p) + r) for r in RECORDS]:
                if q.exists():
                    if not dry_run:
                        trash.mkdir(parents=True, exist_ok=True)
                        dest = trash / q.name
                        if dest.exists():
                            dest = trash / f"{q.name}.{int(q.stat().st_mtime)}"
                        shutil.move(str(q), str(dest))
                    moved.append(q)
    return moved


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    moved = prune(dry_run=dry)
    print(f"render prune: {'would move' if dry else 'moved'} {len(moved)} superseded "
          f"copy file(s) to {TRASH}; at most {KEEP} kept per episode")
