"""The QUEUE under the hook rule - the cloud half. Long-form only, queued only.

    python loop/queue_reopen.py [--limit N] [--dry-run] [--slugs a b]

Owner, 13 Oct 2026 (repackage job 2): every long-form script not yet uploaded
(scripts/ and loop/drafts/) opens `stake-then-payoff` (loop/opening.py) and
runs at least ten minutes. This stage, run daily by loop-repackage.yml on the
subscription route first (loop/llm_router.py: her Claude subscription, the
Gemini free tier, the $0 OpenRouter list; never paid), works
loop/lengthen.queue_slugs() - short scripts first, then hook failures:

  * under 10:00  -> EXTEND: a new hook-first cold open + the untouched body +
                    a warm, funny, sourced tail ending on the next episode;
  * at the floor -> REOPEN: a new cold open only, the rest untouched.

Each is drafted, gated (hook rule, directive truth, the title truth guard,
exclusions, every new source URL fetched) and retried with the rejections fed
back (loop/lengthen.draft). The script and its loop/drafts/ twin are written,
and loop/state/lengthen.json records per slug what changed (kind, minutes and
hook before/after, model) as `scripted` / `pending_bind`. NOTHING else is
written here: plans/, audio/ and renders/ live on the Mac, and
`loop/lengthen.py bind` (bin/batch-session.sh, before it plans or narrates)
makes them agree - a splice where the render can keep its body, otherwise the
old cut is recorded in superseded_renders.json and re-rendered. Until then
the upload lanes hold the slug (loop/lengthen.upload_hold, HOOK_REOPEN_PENDING).

Published videos are never touched (forward only). Guarded by V49 and
loop/tests/test_lengthen.py.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

LOOP = Path(__file__).resolve().parent
sys.path.insert(0, str(LOOP))

import lengthen as L                                       # noqa: E402


def run(limit: int = 0, dry_run: bool = False, slugs=None) -> int:
    from common import Stage, week_id                      # noqa: PLC0415
    with Stage("queue-reopen", week_id(),
               zero_work_hint="No queued script broke the hook rule or the "
                              "ten-minute floor.") as st:
        todo = list(slugs or L.queue_slugs())
        if limit:
            todo = todo[:limit]
        if not todo:
            st.named_stop("QUEUE_HOOK_CLEAN",
                          f"every queued long-form script opens "
                          f"{L.HOOK_VARIANT} and runs at least "
                          f"{L.FLOOR_MIN:.0f} minutes (or waits for the Mac "
                          f"to bind it)",
                          unblock="Nothing to do; a new script is checked the "
                                  "run after it lands.")
        doc = L.load()
        refused = []
        for s in todo:
            r = L.script_cloud(s, dry_run=dry_run, doc=doc)
            if r["status"] in ("scripted", "dry_run"):
                st.work(f"{r.get('kind')} {s}" + (" (dry run)" if dry_run else
                        f": {r.get('minutes_before')} -> {r.get('minutes_after')}"
                        f" min; hook {r.get('hook_after', '')[:90]!r}"))
            elif r["status"] == "rejected":
                refused.append(s)
                st.note(f"refused {s} ({r.get('kind')}): "
                        f"{'; '.join(r.get('problems') or [])[:300]}")
            else:
                st.note(f"{s}: {r['status']} {r.get('why', '')}")
        if not dry_run:
            L.save(doc)
        if refused and not st.units:
            st.named_stop(
                "QUEUE_REOPEN_REFUSED",
                f"{len(refused)} queued script(s) got no passing new opening "
                f"after every attempt: {', '.join(refused)}. The scripts are "
                f"unchanged; the upload lanes hold them under the hook rule.",
                held_items=sorted(refused),
                unblock="Nothing to type: the next daily run drafts again.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--slugs", nargs="*")
    a = ap.parse_args(argv)
    return run(a.limit, a.dry_run, a.slugs or None)


if __name__ == "__main__":
    raise SystemExit(main())
