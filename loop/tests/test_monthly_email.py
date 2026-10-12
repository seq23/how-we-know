"""The monthly email - owner, 2026-10-12: "an overall email sent to me monthly
about what was published (# of shorts, # of long form, what niches, and what
the data suggests)", and an email about the pivot research.

Pinned here with fabricated ledgers, history and verdict (every fixture in a
temp directory; the repo's loop/state is never written):

  a. counts by format and by domain (deep sea / materials / other); a
     cancelled schedule, last month's upload and a future one are NOT counted
     as published; the future one is "scheduled ahead";
  b. the subject shape, and no CODE_TOKEN in it;
  c. the rules section prints EVERY rule with its numbers when nothing
     triggers, and names the rule in the subject when one does;
  d. the advisory paragraph is a named stop - never a crash, never a made-up
     paragraph - when the model route fails or answers off-brief; when it
     answers on-brief via the subscription it is printed and attributed;
  e. the first-month-of-history wording, and trend arrows once a previous
     month exists.
Hard-fails on zero cases.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
sys.path.insert(0, str(LOOP))

import advise                                              # noqa: E402
import author                                              # noqa: E402
import common                                              # noqa: E402
import domains                                             # noqa: E402
import monthly_email as M                                  # noqa: E402
import opening                                             # noqa: E402
from common import config                                  # noqa: E402

fails: list[str] = []
examined = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global examined
    examined += 1
    print(f"  {'ok' if ok else '✗'} {name}" + ("" if ok else f": {detail}"))
    if not ok:
        fails.append(name)


tmp = Path(tempfile.mkdtemp(prefix="monthly-email-"))
cfg = config()
DS, MAT = "deep-sea-ocean-science", "materials-and-manufacturing"
DOMAIN = {"ds-a": DS, "ds-b": DS, "mat-a": MAT, "ds-sep": DS, "ds-future": DS,
          "ds-cancel": DS, "sh-1": DS, "sh-2": DS, "sh-3": DS, "sh-x": "astronomy"}
DOMAIN.update({f"mat-m{i}": MAT for i in range(8)})

long_pub = [
    {"slug": "ds-a", "question": "why is the deep sea dark", "video_id": "L1",
     "scheduled_publish_at": "2026-10-03T15:00:00Z"},
    {"slug": "ds-b", "question": "how deep is the trench", "video_id": "L2",
     "published_at": "2026-10-05T15:00:00+00:00"},
    {"slug": "mat-a", "question": "how is steel made", "video_id": "L3",
     "scheduled_publish_at": "2026-10-09T15:00:00Z"},
    {"slug": "ds-sep", "question": "september episode", "video_id": "L4",
     "scheduled_publish_at": "2026-09-28T15:00:00Z"},
    {"slug": "ds-future", "question": "a future episode", "video_id": "L5",
     "scheduled_publish_at": "2026-11-08T16:00:00Z"},
    {"slug": "ds-cancel", "question": "cancelled", "video_id": "L6",
     "scheduled_publish_at": "2026-10-07T15:00:00Z",
     "schedule_cancelled_at": "2026-09-05T18:50:00+00:00"},
]
short_pub = [
    {"slug": "sh-1", "video_id": "S1", "scheduled_publish_at": "2026-10-05T23:00:00Z"},
    {"slug": "sh-2", "video_id": "S2", "scheduled_publish_at": "2026-10-06T23:00:00Z"},
    {"slug": "sh-3", "video_id": "S3", "scheduled_publish_at": "2026-10-07T23:00:00Z"},
    {"slug": "sh-x", "video_id": "S4", "scheduled_publish_at": "2026-10-08T23:00:00Z"},
    {"slug": "sh-1", "video_id": "S5", "scheduled_publish_at": "2026-10-13T02:00:00Z"},
]
hist = [
    {"kind": "long", "video_id": "L1", "date": "2026-10-12", "views": 9,
     "average_view_duration_s": 120, "average_view_percentage": 20},
    {"kind": "long", "video_id": "L2", "date": "2026-10-12", "views": 4,
     "average_view_duration_s": 90, "average_view_percentage": 15},
    {"kind": "long", "video_id": "L3", "date": "2026-10-12", "views": 7,
     "average_view_duration_s": 100, "average_view_percentage": 18},
    {"kind": "short", "video_id": "S1", "date": "2026-10-12", "views": 187},
    {"kind": "short", "video_id": "S2", "date": "2026-10-12", "views": 105},
]
verdict = {"as_of": "2026-10-12", "views_28d": {"long_form": 198, "shorts": 1027},
           "median_views_per_long_form_video": 7, "median_views_per_short": 36.5,
           "avd_s": 70.0, "avd_floor_s": 146.0, "subscribers_28d_net": 21,
           "subscribers_total": 26, "watch_hours_long_form": 4.0,
           "watch_hours_floor": 3000.0, "watch_hours_pct": 0.1}


def setup(long_rows=long_pub, history=hist, depth=None, owner=None):
    for name, doc in (("ledger.json", {"published": long_rows}),
                      ("shorts_ledger.json", {"published": short_pub}),
                      ("channel_verdict.json", verdict)):
        (tmp / name).write_text(json.dumps(doc))
    (tmp / "history.jsonl").write_text("\n".join(json.dumps(r) for r in history))
    (tmp / "research").mkdir(exist_ok=True)
    (tmp / "research" / "publish_order_x.json").write_text(json.dumps({
        "generated_utc": "2026-10-10T10:00:00+00:00",
        "killed": [{"slug": "what-is-a-frilled-shark",
                    "reason": "title gap 0.00 is at or below the 0.3 ceiling"}]}))
    (tmp / "DECISION-LOG.md").write_text(
        "## 2026-09-26 — old\n- **DECLINED** `old-one` — same question. Moved to x\n"
        "## 2026-10-03 — new\n- **DECLINED** `new-one` — same question as another. "
        "Moved to `loop/drafts/declined/`, never deleted.\n")
    M.LEDGER, M.SHORTS_LEDGER = tmp / "ledger.json", tmp / "shorts_ledger.json"
    M.VERDICT, M.HISTORY = tmp / "channel_verdict.json", tmp / "history.jsonl"
    M.OUTDIR, M.PUBLISH_ORDERS = tmp / "monthly", tmp / "research"
    M.DECISION_LOG = tmp / "DECISION-LOG.md"
    domains.domain_of_slug = lambda slug, default=None: DOMAIN.get(slug, default)
    domains.queue_depth = lambda include_published=False: depth or {DS: 6, MAT: 7}
    domains.by_slug = lambda: dict(DOMAIN)
    opening.variant_of = lambda slug: opening.PRE_RULE
    common.owner_actions = lambda: owner or {}


def fake_model(texts, route="claude-subscription", raise_=None):
    calls = []

    def call(messages, model, key, timeout=300, temperature=0.4):
        calls.append(messages)
        if raise_:
            raise raise_
        return {"choices": [{"message": {"content": texts[min(len(calls), len(texts)) - 1]}}],
                "route": route, "model_used": "claude-subscription/opus"}
    author.call_openrouter = call
    author.api_key = lambda: "k"
    return calls


TODAY = dt.date(2026, 10, 12)
print("\n── a. counts by format and domain")
setup()
f = M.build(TODAY, True, cfg, ask_model=False)
p = f["published"]
check("long-form count excludes Sep, future and cancelled", p["long_form"] == 3, p["long_form"])
check("Shorts count excludes the future Short", p["shorts"] == 4, p["shorts"])
by = {k: {d: len(v) for d, v in g.items()} for k, g in p["by_domain"].items()}
check("long-form by domain", by["long_form"] == {"deep sea": 2, "materials": 1}, by)
check("Shorts by domain, unknown domain is 'other'",
      by["shorts"] == {"deep sea": 3, "other": 1}, by)
check("scheduled ahead counts and last dated day",
      p["ahead"]["long_form"] == {"count": 1, "last": "2026-11-08"}
      and p["ahead"]["shorts"] == {"count": 1, "last": "2026-10-13"}, p["ahead"])
body = M.render(f)
check("titles listed as slug → question",
      "ds-a → why is the deep sea dark" in body and "mat-a → how is steel made" in body)
check("partial month says so in the body",
      "Partial month, produced on demand" in body and "2026-10-01 to 2026-10-12" in body)
check("four sections in order",
      [body.index(h) for h in ("## 1. Published", "## 2. What the data",
                               "## 3. Keep, change or pivot", "## 4. What needs you")]
      == sorted(body.index(h) for h in ("## 1. Published", "## 2. What the data",
                                         "## 3. Keep, change or pivot", "## 4. What needs you")))
check("top episodes ranked by views",
      [r["video_id"] for r in f["data"]["top_episodes"]] == ["L1", "L3", "L2"],
      f["data"]["top_episodes"])
weeks = {w["week"]: w["shorts"] for w in f["data"]["shorts_weeks"]}
check("Shorts per ISO week of the month vs target",
      weeks == {"2026-W40": 0, "2026-W41": 4, "2026-W42": 0}
      and all(w["target"] == cfg["cadence"]["shorts_per_week"]
              for w in f["data"]["shorts_weeks"]), weeks)
full = M.build(dt.date(2026, 11, 1), False, cfg, ask_model=False)
check("on the 1st the 13 Oct Short counts as October's",
      full["published"]["shorts"] == 5, full["published"]["shorts"])
check("on the 1st it reports the month just ended, whole",
      full["month"] == "2026-10" and full["to"] == "2026-10-31"
      and not full["partial"] and full["published"]["long_form"] == 3,
      (full["month"], full["to"]))

print("\n── b. subject")
SUBJ = re.compile(r"^Monthly: \d+ episodes \+ \d+ Shorts published in [A-Z][a-z]+"
                  r"(?: so far \(to \d{1,2} [A-Z][a-z]{2}\))?; [a-z][^\n]+$")
for s in (M.subject(f), M.subject(full)):
    check(f"subject shape: {s}", bool(SUBJ.match(s)))
    check("subject has no CODE_TOKEN", not re.search(r"[A-Z]{3,}_[A-Z_]+", s), s)
check("partial subject counts", M.subject(f).startswith(
    "Monthly: 3 episodes + 4 Shorts published in October so far (to 12 Oct); "
    "no pivot rule triggered"), M.subject(f))
check("full-month subject", M.subject(full) ==
      "Monthly: 3 episodes + 5 Shorts published in October; no pivot rule triggered",
      M.subject(full))

print("\n── c. every rule, with numbers, triggered or not")
rules = body[body.index("## 3."):body.index("### What the data suggests")]
for needle in ("**Domain swap rule**", "below 4 after 8 measured", "deep sea: 2 measured episodes (needs 8); queue 6 topics",
               "materials: 1 measured episodes (needs 8); queue 7 topics",
               "**Slot move rule**", "spread now 5 s", "30 s of average view duration",
               "**Opening-line experiment**", "of 3 eligible episodes aired",
               "decision date not set yet",
               "**Topic kills**", "2 this month", "what-is-a-frilled-shark", "new-one",
               "**Cadence:** 4 episodes a week", "2 Sep 2026",
               "docs/research/how-we-know-numbers.md",
               "**Rules that triggered:** none."):
    check(f"rules section prints {needle!r}", needle in rules)
check("September's decline is not this month's kill", "old-one" not in rules)
check("rules section carries no raw domain ids", DS not in rules and MAT not in rules)

mat_hist = hist + [{"kind": "long", "video_id": f"M{i}", "date": "2026-10-12",
                    "views": 1, "average_view_duration_s": 60}
                   for i in range(8)]
mat_rows = long_pub + [{"slug": f"mat-m{i}", "question": f"m{i}", "video_id": f"M{i}",
                        "scheduled_publish_at": "2026-09-0%dT15:00:00Z" % (i + 1)}
                       for i in range(8)]
setup(long_rows=mat_rows, history=mat_hist, depth={DS: 6, MAT: 2})
fired = M.build(TODAY, True, cfg, ask_model=False)
check("domain swap triggers on a decayed, measured queue",
      fired["rules"]["domain_swap"]["triggered"], fired["rules"]["domain_swap"]["why"])
check("subject names the triggered rule in plain words",
      M.subject(fired).endswith("domain swap rule triggered for materials"),
      M.subject(fired))
check("triggered subject still has no CODE_TOKEN",
      not re.search(r"[A-Z]{3,}_[A-Z_]+", M.subject(fired)))
check("triggered rule printed as TRIGGERED", "**TRIGGERED**" in M.render(fired))

print("\n── d. the advisory paragraph")
setup()
SECTIONS = M.sections_without_advice(M.build(TODAY, True, cfg, ask_model=False))
fake_model([], raise_=RuntimeError("route down"))
try:
    f_fail = M.build(TODAY, True, cfg)
    crashed = ""
except Exception as e:                                     # noqa: BLE001
    f_fail, crashed = None, repr(e)
check("route failure does not crash", not crashed, crashed)
if f_fail:
    b = M.render(f_fail)
    adv = b[b.index("### What the data suggests"):b.index("## 4.")]
    check("route failure is a named stop line", "Named stop MONTHLY_ADVICE_UNAVAILABLE" in adv
          and "route down" in adv, adv)
    check("route failure prints no paragraph", "Written by the model" not in adv)

bad = "Views rose 400% and we should post 12 a week; no pivot rule has triggered."
calls = fake_model([bad, bad])
f_bad = M.build(TODAY, True, cfg)
check("off-brief numbers are refused after one retry", len(calls) == 2
      and not f_bad["advice"]["ok"] and "400" in f_bad["advice"]["why"], f_bad["advice"])
check("refused paragraph never reaches the body", bad not in M.render(f_bad))
check("retry carries the refusal reason",
      len(calls) == 2 and "refused because" in calls[1][1]["content"])

no_pivot = ("Long-form holds 70 s against the 146 s floor and Shorts drew 1,027 views "
            "in 28 days; the one change for next month is to get Shorts back to 9 a "
            "week. No pivot rule has triggered; the data is too thin to pivot on.")
silent = no_pivot.replace(" No pivot rule has triggered; the data is too thin to pivot on.", "")
calls = fake_model([silent, silent])
check("a paragraph that does not say whether a pivot rule triggered is refused",
      not M.build(TODAY, True, cfg)["advice"]["ok"])
calls = fake_model([no_pivot])
f_ok = M.build(TODAY, True, cfg)
b = M.render(f_ok)
check("an on-brief paragraph is printed", f_ok["advice"]["ok"] and no_pivot in b, f_ok["advice"])
check("attributed to her subscription", "via her Claude subscription" in b)
check("the prompt carries the sections and the no-pivot sentence",
      "## 3. Keep, change or pivot" in calls[0][1]["content"]
      and M.NO_PIVOT in calls[0][1]["content"])
check("monthly_problems accepts the sections' own numbers",
      advise.monthly_problems(no_pivot, SECTIONS, []) == [],
      advise.monthly_problems(no_pivot, SECTIONS, []))

print("\n── e. history wording and needs-you")
setup()
f1 = M.build(TODAY, True, cfg, ask_model=False)
check("first month of history wording", "First month of history" in M.render(f1)
      and "starts 2026-10-12" in M.render(f1))
M.write(f1)
check("write() leaves .md, .subject and .json",
      all((tmp / "monthly" / f"2026-10-email.{x}").exists() for x in ("md", "subject", "json")))
f2 = M.build(dt.date(2026, 11, 30), True, cfg, ask_model=False)
b2 = M.render(f2)
check("a previous month removes the first-month wording", "First month of history" not in b2)
check("trend arrows appear against the previous month", "↓" in b2 or "↑" in b2 or "→" in b2)
check("nothing waiting prints Nothing.", b2.rstrip().endswith("Nothing."))
setup(owner={"cloud-upload": {"code": "OAUTH_MISSING", "message": "the YouTube sign-in expired",
                              "unblock": "sign in again", "at": "2026-10-10T00:00:00+00:00"}})
b3 = M.render(M.build(TODAY, True, cfg, ask_model=False))
check("an owner_action record is printed in plain words",
      "**cloud-upload:** the YouTube sign-in expired" in b3[b3.index("## 4."):])

print("\n" + "=" * 60)
if examined == 0:
    print("FAIL: examined zero cases")
    sys.exit(1)
print(f"{examined} case(s), {len(fails)} failed")
sys.exit(1 if fails else 0)
