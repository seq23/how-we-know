"""The Money lane's author: the next Money episode's script, at $0.

    python loop/money_author.py            # stage "money-author" (loop-money-author.yml)
    python loop/money_author.py --plan     # the next topic and what is in flight; write nothing
    python loop/money_author.py --queue    # (re)write research/publish_order_money_and_business.json

WHY (her calls 8 and 9 Nov 2026, spry brain): How We Know's Money lane is a
12-video test - money and business stories proven by the public record - and
it takes both of How We Know's long-form nights. The 12 topics were picked by
demand and evidence on 9 Nov (config/money_topics.json, rank order). Nothing
drafted them: this is that lane, built on the food lane's pattern
(loop/food_author.py): the cloud writes the script, the Mac's nightly batch
narrates and renders it (loop/night_split.longform_slugs gives Money the
night first).

WHAT ONE RUN DOES
  1. The queue: every topic in config/money_topics.json is a row of
     research/publish_order_money_and_business.json (the one queue the batch
     reads), in rank order; a row is never removed.
  2. Backpressure: at most MAX_IN_FLIGHT money scripts written and not yet
     uploaded - MONEY_EPISODE_IN_FLIGHT (self-resolving: an upload clears it).
  3. The next unwritten topic is drafted by loop/author.draft() - the same $0
     route (Gemini free tier, then the free OpenRouter list, never paid), the
     same house rules and the same validation every script gets - with the
     Money brief (loop/author.py DOMAIN_BRIEF) and the Money source list
     (loop/domain_sources.py: SEC, courts, the Federal Reserve, BLS/FRED, the
     FCIC report, Congress, the National Archives, the Library of Congress).
     The title is the topic's one plain question.
  4. Risk brain R-ADV-04, in code (money_problems): the narration says "This
     is not financial advice." (added to the closing when the draft left it
     out), and a draft that gives a tip or promises money is refused.
  5. The full validator set (loop/validate.run_all) on the one script; only a
     script that passes reaches scripts/<slug>.md, where the batch reads it.
  6. A topic that is not written (a failed draft, a refused one) is a note:
     the next topics are tried in rank order, up to TOPICS_A_RUN a run, and
     the skipped topic is first again at the next daily run.

Rule 0: every run writes a script or ends on a named stop.
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import date
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

DOMAIN = "money-and-business"
TOPICS = ROOT / "config" / "money_topics.json"
ORDER = ROOT / "research" / "publish_order_money_and_business.json"
SCRIPTS = ROOT / "scripts"
DRAFTS = LOOP / "drafts"                                    # where author.draft writes
MAX_IN_FLIGHT = 2                   # two How We Know nights a week
TOPICS_A_RUN = 3                    # topics tried in one run before it is a stop
LANE_MARK = "**Made by:** loop/money_author.py"
DISCLAIMER = "This is not financial advice."

# R-ADV-04 (risk brain): information, never advice; no get-rich promise.
PROMISES = re.compile(
    r"\byou (?:should|could|can|must) (?:buy|sell|invest|trade|short)\b"
    r"|\bget rich\b|\bgetting rich\b|\bguaranteed? (?:returns?|profits?|income|money)\b"
    r"|\b(?:investing|investment|stock|trading) tips?\b|\bmake money fast\b"
    r"|\bfinancial freedom\b|\bpassive income\b", re.I)


def topics() -> list[dict]:
    return sorted(json.loads(TOPICS.read_text())["topics"], key=lambda t: t["rank"])


def queue_rows() -> list[dict]:
    """One publish-order row per Money topic, in rank order."""
    picked = json.loads(TOPICS.read_text()).get("picked_on")
    return [{"slug": t["slug"], "domain": DOMAIN, "title": t["title"],
             "query": re.sub(r"[^a-z ]", "", t["title"].lower()).strip(),
             "gate": {"verdict": "passed", "failed": [],
                      "reason": (f"Money test topic {t['rank']} of 12, picked {picked} by "
                                 f"YouTube autocomplete demand ({t['demand']}) and public-record "
                                 f"evidence (config/money_topics.json); owner decision 8-9 Nov 2026")},
             "demand": {"autocomplete": t["demand"], "caveat": "autocomplete presence, NOT search volume"},
             "sources_expected": t.get("sources") or [],
             "made_by": "loop/money_author.py (scripts/<slug>.md; the nightly batch renders it)",
             "queued": picked}
            for t in topics()]


def write_queue() -> dict:
    """Keep every existing row; add any topic not yet queued, in rank order."""
    d = json.loads(ORDER.read_text()) if ORDER.exists() else {}
    have = {r.get("slug") for r in d.get("queue") or []}
    queue = list(d.get("queue") or []) + [r for r in queue_rows() if r["slug"] not in have]
    d = {"generator": "loop/money_author.py --queue (config/money_topics.json)",
         "domain": DOMAIN,
         "why": ("How We Know's Money lane, the 12-video test (owner 8-9 Nov 2026). Rows "
                 "come from config/money_topics.json in rank order; loop/money_author.py "
                 "writes each script; the Mac's How We Know nights narrate Money first."),
         **{k: v for k, v in d.items() if k not in ("queue", "queue_length", "generator", "domain", "why")},
         "queue": queue, "queue_length": len(queue)}
    ORDER.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    return d


def published_slugs() -> set[str]:
    import ledger                                           # noqa: PLC0415
    return {r["slug"] for r in ledger.load().get("published") or []}


def in_flight(pub: set[str] | None = None) -> list[str]:
    """Money scripts written and not yet uploaded (the Mac's to render)."""
    pub = published_slugs() if pub is None else pub
    return [t["slug"] for t in topics()
            if (SCRIPTS / f"{t['slug']}.md").exists() and t["slug"] not in pub]


def next_topic(pub: set[str] | None = None) -> dict | None:
    pub = published_slugs() if pub is None else pub
    return next((t for t in topics() if not (SCRIPTS / f"{t['slug']}.md").exists()
                 and t["slug"] not in pub), None)


def next_topics(pub: set[str] | None = None) -> list[dict]:
    """Every topic with no script and no upload, in rank order."""
    pub = published_slugs() if pub is None else pub
    return [t for t in topics() if not (SCRIPTS / f"{t['slug']}.md").exists() and t["slug"] not in pub]


def ensure_disclaimer(text: str) -> str:
    """'This is not financial advice.' closes the narration (R-ADV-04). Added
    as the last line of '### Closing' when the draft left it out."""
    if "not financial advice" in _narration(text).lower():
        return text
    m = re.search(r"^### Closing\s*$(.*?)(?=^### |^## |\Z)", text, re.S | re.M)
    if not m:
        return text
    body = m.group(1).rstrip()
    return text[:m.start(1)] + body + f"\n\n{DISCLAIMER}\n\n" + text[m.end(1):].lstrip("\n")


def _narration(text: str) -> str:
    m = re.search(r"^## Narration\s*$(.*?)(?=^## |\Z)", text, re.S | re.M)
    return m.group(1) if m else ""


def money_problems(text: str) -> list[str]:
    """R-ADV-04 on the narration, which is what is spoken and shown."""
    nar = _narration(text)
    out = []
    if not nar.strip():
        out.append("no ## Narration section")
    if "not financial advice" not in nar.lower():
        out.append(f"the narration never says {DISCLAIMER!r} (R-ADV-04)")
    for m in PROMISES.finditer(nar):
        out.append(f"advice or a money promise in the narration: {m.group(0)!r} (R-ADV-04)")
    if not re.search(r"^\*\*Domain:\*\*\s*money-and-business\s*$", text, re.M):
        out.append("the script does not declare **Domain:** money-and-business")
    return out


def finish(text: str, topic: dict) -> str:
    """The drafted script as the batch will read it: the topic's plain question
    as its title, the lane's mark, and the disclaimer."""
    text = re.sub(r"^# .*$", f"# {topic['title']}", text, count=1, flags=re.M)
    if LANE_MARK not in text:
        text = re.sub(r"^(\*\*Domain:\*\*.*)$", rf"\1\n{LANE_MARK}", text, count=1, flags=re.M)
    return ensure_disclaimer(text)


def run(plan_only: bool = False) -> int:
    if plan_only:
        t = next_topic()
        print(f"in flight: {in_flight() or 'none'}")
        print(f"next money topic: {t['slug'] + '  (' + t['title'] + ')' if t else 'none - all 12 written'}")
        return 0
    from common import Stage, week_id                       # noqa: PLC0415
    import author                                           # noqa: PLC0415
    import ledger                                           # noqa: PLC0415
    import pov_match                                        # noqa: PLC0415
    import validate                                         # noqa: PLC0415
    with Stage("money-author", week_id(),
               zero_work_hint="loop/money_author.py writes one Money episode a run") as st:
        before = ORDER.read_text() if ORDER.exists() else ""
        write_queue()
        if ORDER.read_text() != before:
            st.work(f"queued the Money topics in {ORDER.relative_to(ROOT)}")
        pub = published_slugs()
        busy = in_flight(pub)
        if len(busy) >= MAX_IN_FLIGHT:
            st.named_stop("MONEY_EPISODE_IN_FLIGHT",
                          f"{', '.join(busy)} written and waiting for the Mac's How We Know "
                          f"nights; at most {MAX_IN_FLIGHT} Money scripts are in flight",
                          unblock="Nothing to do: an upload clears it and the next run "
                                  "writes the next topic.")
        todo = next_topics(pub)
        if not todo:
            st.named_stop("MONEY_TOPICS_DONE",
                          "all 12 Money test topics are written; the 30-day lane check "
                          "(loop/lane_check.py) judges the test",
                          unblock="Nothing to do: more topics follow only if the test passes.")
        used = [r.get("pov_id") for r in ledger.load()["published"] if r.get("pov_id")]
        deadline = time.monotonic() + 150 * 60
        # ONE TOPIC THE FREE MODELS CANNOT WRITE TODAY NEVER COSTS THE NIGHT ITS
        # SCRIPT (13 Nov 2026: the run ended on FTX's fourth failed draft and
        # opened an issue, with ten more topics unwritten). The next topics are
        # tried in rank order, up to TOPICS_A_RUN; the skipped one is first
        # again at the next run. Only a run that writes nothing is the stop.
        failed: list[TopicStop] = []
        t = None
        for t in todo[:TOPICS_A_RUN]:
            print(f"next money topic: {t['slug']} ({t['title']})")
            try:
                line = write_topic(t, used, deadline, author, pov_match, validate)
            except TopicStop as e:
                failed.append(e)
                st.note(f"{e.code} {e.message}")
                continue
            st.work(line)
            break
        else:
            first = failed[0]
            st.named_stop(first.code,
                          f"{len(failed)} Money topic(s) tried, none written: "
                          + " | ".join(f.message[:260] for f in failed),
                          unblock=first.unblock)
    print(f"OUTPUT money-author: scripts/{t['slug']}.md written"
          + (f" ({len(failed)} earlier topic(s) refused today, tried again at the next run)" if failed else ""))
    return 0


class TopicStop(Exception):
    """One topic was not written this run; the next topic is tried."""

    def __init__(self, code: str, message: str, unblock: str = ""):
        super().__init__(f"{code}: {message}")
        self.code, self.message, self.unblock = code, message, unblock


def write_topic(t: dict, used: list, deadline: float, author, pov_match, validate) -> str:
    """Draft, check (R-ADV-04, then every validator) and write ONE topic's
    script. Returns the work line; raises TopicStop when it is not written."""
    try:
        pov = pov_match.select(t["slug"], f"{t['title']} {t['slug']}", used, domain=DOMAIN)
    except Exception as e:                                  # noqa: BLE001
        raise TopicStop("MONEY_NO_POV_LINE", f"{t['slug']}: no transferable POV line is free "
                        f"({str(e)[:120]})", "The next run tries again as lines free up.") from e
    try:
        out = author.draft(t["title"], t["slug"], pov, domain=DOMAIN, deadline=deadline)
    except author.AuthorStop as e:
        raise TopicStop(e.code, f"{t['slug']}: {e.message}", e.unblock) from e
    draft = DRAFTS / f"{t['slug']}.md"
    if (ROOT / out["path"]).resolve() != draft.resolve():
        raise TopicStop("MONEY_DRAFT_PATH_MOVED", f"{t['slug']}: author wrote {out['path']}, "
                        f"expected {draft.relative_to(ROOT)}",
                        "Point DRAFTS in loop/money_author.py at author.DRAFTS.")
    text = finish(draft.read_text(), t)
    bad = money_problems(text)
    if bad:
        raise TopicStop("MONEY_DRAFT_REFUSED", f"{t['slug']}: {bad[0]}",
                        "The next run drafts the topic again.")
    draft.write_text(text)
    item = {"slug": t["slug"], "question": t["title"], "script": out["path"],
            "generated": True, "pov_id": pov.get("pov_id"), "pov_line": pov.get("line"),
            "pov_tier": pov.get("tier"), "pov_matched_by": pov.get("matched_by"),
            "domain": DOMAIN}
    passed, report = validate.run_all([item])
    if not passed:
        fails = [f"{r['validator']}: {(r['failures'] or [''])[0][:140]}"
                 for r in report if "FAIL" in r["status"]]
        raise TopicStop("MONEY_DRAFT_FAILED_VALIDATION",
                        f"{t['slug']}: {len(fails)} validator(s) failed: {'; '.join(fails[:3])}",
                        "The draft stays in loop/drafts/; the next run drafts again.")
    (SCRIPTS / f"{t['slug']}.md").write_text(text)
    if pov.get("pov_id") and pov.get("line"):
        pov_match.record_assignment(t["slug"], {"pov_id": pov["pov_id"], "line": pov["line"],
                                                "tier": pov.get("tier", "transferable")})
        used.append(pov["pov_id"])
    return (f"wrote scripts/{t['slug']}.md ({out.get('model')}, attempt {out.get('attempt')}, "
            f"{len(report)} validators passed)")


def main(argv: list[str]) -> int:
    if "--queue" in argv:
        d = write_queue()
        print(f"OUTPUT money queue: {d['queue_length']} row(s) in {ORDER.relative_to(ROOT)}")
        return 0
    return run(plan_only="--plan" in argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
