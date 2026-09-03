"""The dashboard. Optional, read-only by default, and nothing blocks on it.

There is no weekly approval any more. Topics are picked automatically under the
hard exclusion gate, and POV lines come from the owner's own bank - which IS
her approved voice, so there was never a real question to ask her. Her
involvement approaches zero.

What survives is a **notification with an override**: this page shows what was
picked, what was drafted, what it cost, and which citations were verified, with
a Drop button per row. If she never opens it, the week ships anyway.

Constraints it still obeys:

* **Credentialless.** A static file committed to the repo. No login, no server,
  no token, no fetch - the week's data is inlined at build time, so it works
  offline, from a phone, or from a local `file://` open.
* **The return path is a prefilled GitHub issue.** Drop opens GitHub's new-issue
  form pre-filled; `loop-override.yml` ingests it. She is already signed in, so
  it is one further click - but only if she wants something changed.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cadence  # noqa: E402
from common import ROOT, config  # noqa: E402

PAGE = ROOT / "docs" / "approve" / "index.html"
# Kept at the same path so any link she already has still works.

TEMPLATE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>How We Know - week __WEEK__</title>
<style>
:root{color-scheme:light dark;--bg:#0b1620;--card:#11212e;--ink:#e8f1f6;
--dim:#8fa9b8;--accent:#57c7e3;--ok:#4ec97a;--warn:#f0b429;--bad:#ff6b6b}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
.wrap{max-width:780px;margin:0 auto;padding:28px 18px 60px}
h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--dim);font-size:14px;margin-bottom:18px}
.note{background:#0e2a1c;border:1px solid #1f5c3a;border-radius:10px;
padding:12px 14px;font-size:14px;margin-bottom:20px}
.bar{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;color:var(--dim);
background:var(--card);border-radius:10px;padding:12px 14px;margin-bottom:20px}
.bar b{color:var(--ink)}
.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}
.card{background:var(--card);border-radius:12px;padding:16px 18px;margin-bottom:14px}
.q{font-size:17px;font-weight:600;margin:0 0 6px}
.meta{font-size:12px;color:var(--dim);margin-bottom:10px}
.tag{display:inline-block;font-size:11px;padding:2px 8px;border-radius:20px;
background:#0d2b38;color:var(--accent);margin-right:6px}
.tag.gen{background:#2b2410;color:var(--warn)}
.pov{font-size:14px;color:var(--dim);border-left:2px solid #24404f;
padding-left:12px;margin:10px 0 12px}
button.drop{background:transparent;color:var(--dim);border:1px solid #33505f;
border-radius:8px;padding:6px 14px;font-size:13px;cursor:pointer}
button.drop:hover{border-color:var(--bad);color:var(--bad)}
button.drop.on{border-color:var(--bad);color:var(--bad);background:#2a1416}
.actions{margin-top:22px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
a.btn,button.btn{background:var(--accent);color:#06222d;border:0;border-radius:9px;
padding:11px 20px;font-size:15px;font-weight:650;text-decoration:none;cursor:pointer}
button.btn[disabled]{opacity:.35;cursor:not-allowed}
.stop{background:#2a1a12;border:1px solid #6b3f1c;border-radius:10px;
padding:12px 14px;margin-bottom:16px;font-size:14px}
pre{white-space:pre-wrap;word-break:break-word;background:#08131b;padding:12px;
border-radius:9px;font-size:12px;color:var(--dim)}
</style></head><body><div class="wrap">

<h1>Week __WEEK__</h1>
<div class="sub">__COUNT__ video__PLURAL__ picked automatically ·
ceiling __CEILING__/week (deliberate)</div>

<div class="note"><b>Nothing here is waiting on you.</b> Topics were picked from
demand data under the hard exclusion gate, and every POV line came from your own
bank. This page is a notification. Drop a row only if you actively want it gone -
the override window closes Tuesday 02:00, when rendering starts.</div>

<div class="bar">
  <span>breaker <b class="__BRK_CLASS__">__BRK__</b></span>
  <span>validators <b class="__VAL_CLASS__">__VAL__</b></span>
  <span>gate refused <b>__REFUSED__</b> candidates</span>
  <span>authored <b>__NGEN__</b></span>
  <span>cost <b>$__COST__</b></span>
</div>

__STOPS__

<form id="f">__CARDS__</form>

<div class="actions">
  <button class="btn" id="go" disabled>Drop selected</button>
  <span class="sub" style="margin:0" id="hint">Select a row to enable</span>
</div>

<div class="card" style="margin-top:22px">
  <h3 style="margin:0 0 8px;font-size:13px;color:var(--dim)">If the button is blocked</h3>
  <p style="font-size:13px;color:var(--dim);margin:0 0 8px">Run on the Mac:
  <code>bin/loop-override.sh __WEEK__ --drop &lt;slug&gt;</code></p>
  <pre id="raw">nothing selected</pre>
</div>

</div>
<script>
const DATA = __DATA__;
const REPO = "__REPO__";
function selected(){
  return [...document.querySelectorAll("button.drop.on")].map(b => b.dataset.slug);
}
function body(){
  const s = selected();
  return ["Dropping these from the week. Everything else ships as picked.", "",
          ...s.map(x => `- drop: ${x}`), "", `week: ${DATA.week}`].join("\n");
}
function refresh(){
  const s = selected();
  document.getElementById("go").disabled = s.length === 0;
  document.getElementById("hint").textContent = s.length
    ? `${s.length} selected` : "Select a row to enable";
  document.getElementById("raw").textContent = s.length
    ? `OVERRIDE ${DATA.week}\n\n` + body() : "nothing selected";
}
document.querySelectorAll("button.drop").forEach(b => {
  b.addEventListener("click", e => {
    e.preventDefault(); b.classList.toggle("on");
    b.textContent = b.classList.contains("on") ? "Will be dropped" : "Drop";
    refresh();
  });
});
document.getElementById("go").addEventListener("click", e => {
  e.preventDefault();
  const u = `https://github.com/${REPO}/issues/new?title=`
    + encodeURIComponent(`OVERRIDE ${DATA.week}`)
    + `&body=` + encodeURIComponent(body()) + `&labels=loop-override`;
  window.open(u, "_blank", "noopener");
});
refresh();
</script>
</body></html>
"""

CARD = """
<div class="card">
  <p class="q">__N__. __QUESTION__</p>
  <div class="meta">
    <span class="tag __GENCLASS__">__ORIGIN__</span>
    __SLUG__ · __SOURCES__ sources__URLNOTE__ · __BEATS__ beats__COST__
  </div>
  <div class="pov"><b>POV __POVID__</b> — __POVLINE__<br>
    <span style="font-size:11px;opacity:.7">matched: __MATCHED__</span></div>
  <button class="drop" data-slug="__SLUG__">Drop</button>
</div>
"""

def build(queue: dict, topics: dict | None = None) -> Path:
    cfg = config()
    items = [i for i in queue["items"] if i.get("status") != "dropped"]
    topics = topics or {}
    cards = []
    for i, it in enumerate(items, 1):
        gen = it.get("generated")
        cost = (f" · ${it['author_cost_usd']}" if it.get("author_cost_usd")
                else "")
        urlnote = ""
        for row in queue.get("validators", []):
            if row["validator"].startswith("V8") and gen:
                urlnote = (" (all verified)" if row["status"] == "PASS"
                           else " (UNVERIFIED)")
        cards.append(CARD
                     .replace("__N__", str(i))
                     .replace("__QUESTION__", html.escape(it["question"]))
                     .replace("__ORIGIN__",
                              f"drafted by {it.get('author_model','LLM')}" if gen
                              else "human-authored")
                     .replace("__GENCLASS__", "gen" if gen else "")
                     .replace("__SLUG__", it["slug"])
                     .replace("__SOURCES__", str(it.get("source_count", "?")))
                     .replace("__URLNOTE__", urlnote)
                     .replace("__BEATS__", str(it.get("planned_beats", "?")))
                     .replace("__COST__", cost)
                     .replace("__POVID__", it.get("pov_id", "—"))
                     .replace("__POVLINE__",
                              html.escape(it.get("pov_line", "") or ""))
                     .replace("__MATCHED__",
                              html.escape(it.get("pov_matched_by", "") or "—")))

    brk = queue.get("breaker", "closed")
    val = "passed" if queue.get("validators_passed") else "FAILED"
    stops = ""
    gaps = [(it["slug"], it["attribution_gaps"]) for it in items
            if it.get("attribution_gaps")]
    if gaps:
        rows = "; ".join(f"{s_} → {', '.join(g)}" for s_, g in gaps)
        stops += ('<div class="stop"><b>Attribution gap (does not block):</b> '
                  'narration names a body that is not in that script\'s '
                  f'<code>## Sources</code> — {html.escape(rows)}.</div>')
    if queue.get("unauthored"):
        stops += ('<div class="stop"><b>Named stop:</b> '
                  f'{len(queue["unauthored"])} slot(s) could not be authored '
                  'automatically; briefs are in <code>loop/briefs/</code>. '
                  f'The week still ships {len(items)}.</div>')
    if brk == "tripped":
        stops += ('<div class="stop"><b>Circuit breaker tripped.</b> Publishing '
                  'is halted. Drafting and rendering continue; nothing goes '
                  'public until it is reset.</div>')

    auth = queue.get("authoring", {})
    data = {"week": queue["week"], "generated": queue["generated"],
            "items": [{"slug": it["slug"]} for it in items]}

    page = (TEMPLATE
            .replace("__WEEK__", queue["week"])
            .replace("__COUNT__", str(len(items)))
            .replace("__PLURAL__", "" if len(items) == 1 else "s")
            .replace("__CEILING__", str(cadence.effective()))
            .replace("__BRK__", brk)
            .replace("__BRK_CLASS__", "ok" if brk == "closed" else "bad")
            .replace("__VAL__", val)
            .replace("__VAL_CLASS__", "ok" if val == "passed" else "bad")
            .replace("__REFUSED__",
                     str(topics.get("gate", {}).get("refused_this_week", "—")))
            .replace("__NGEN__", str(auth.get("generated_this_week", 0)))
            .replace("__COST__", f"{auth.get('cost_usd', 0):.3f}")
            .replace("__STOPS__", stops)
            .replace("__CARDS__", "\n".join(cards))
            .replace("__DATA__", json.dumps(data))
            .replace("__REPO__", cfg["repo"]))

    PAGE.parent.mkdir(parents=True, exist_ok=True)
    PAGE.write_text(page)
    return PAGE


if __name__ == "__main__":
    from common import LOOP, read_json
    q = read_json(LOOP / "render_queue.json")
    t = read_json(LOOP / "next_topics.json", default={})
    print(build(q, t))
