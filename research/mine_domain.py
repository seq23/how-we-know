"""Deep, domain-specific topic miner. Same free autocomplete method as
mine.py, generalised so a domain other than deep sea can build its own corpus
without overwriting mined_queries.json — which research/publish_order.py's
deep-sea gate reads as its corpus and must not lose out from under it.

`research/broad_mined.json` (research/mine_broad.py) mines all 20 domains with
the SAME shallow 8-seed budget so they are comparable to each other for
DOMAIN-level ranking. This script is the deeper, single-domain pass — the
equivalent of what produced research/mined_queries.json for deep sea — used
to generate real candidate EPISODE topics for one domain once it has already
won the domain-level ranking.

Usage: python mine_domain.py <seeds.json> <out.json>
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from mine import ENDPOINT, QUESTION, expand  # noqa: E402


def main() -> int:
    if len(sys.argv) < 3:
        sys.exit("usage: mine_domain.py <seeds.json> <out.json>")
    seeds_path, out_path = sys.argv[1], sys.argv[2]
    seeds = json.load(open(seeds_path, encoding="utf-8"))["seeds"]
    print(f"mining {len(seeds)} seeds -> {out_path}", flush=True)
    found = expand(seeds)
    rows = []
    for q, srcs in found.items():
        rows.append({
            "query": q,
            "is_question": bool(QUESTION.match(q)),
            "words": len(q.split()),
            "seed_hits": len(srcs),
            "seeds": sorted(srcs)[:4],
        })
    rows.sort(key=lambda r: (-r["seed_hits"], -r["is_question"], r["words"]))
    out = {
        "mined_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": ENDPOINT, "surface": "youtube_autocomplete",
        "generator": "research/mine_domain.py",
        "seeds_file": seeds_path,
        "seed_count": len(seeds), "unique_queries": len(rows), "queries": rows,
    }
    json.dump(out, open(out_path, "w", encoding="utf-8"), indent=2)
    print(f"{len(rows)} unique real queries -> {out_path}")
    qs = [r for r in rows if r["is_question"]]
    print(f"  of which questions: {len(qs)}")
    for r in qs[:20]:
        print(f"   {r['seed_hits']:>2}x  {r['query']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
