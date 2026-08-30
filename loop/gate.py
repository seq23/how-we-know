"""The approval gate — one page, four POV lines, one button.

The gate is the loop's single point of friction, so it is built to be smaller
than the temptation to skip it. Constraints it obeys:

* **Credentialless.** A static file committed to the repo and served by GitHub
  Pages. No login, no server, no token, no build step. It cannot break because
  something expired.
* **Self-contained.** The week's data is *inlined* into the HTML at build time,
  so the page never fetches anything and works offline, from a phone, or from a
  local `file://` open.
* **The return path is a prefilled GitHub issue.** The page cannot write to the
  repo, and giving it a token would break the first constraint. So "Approve all"
  opens GitHub's new-issue form with the title and body already filled in — the
  owner is already signed in on her devices, so it is one further click. A
  workflow listening on `issues.opened` parses it, writes the approval file, and
  closes the issue.
* **Under 20 minutes.** Four cards, each with the one decision that genuinely
  needs her: which POV line is actually hers. Everything else is displayed as
  evidence, not as a question.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ROOT, config  # noqa: E402

PAGE = ROOT / "docs" / "approve" / "index.html"

TEMPLATE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Approve — How We Know · __WEEK__</title>
<style>
:root{color-scheme:light dark;--bg:#0b1620;--card:#11212e;--ink:#e8f1f6;
--dim:#8fa9b8;--line:#1e3140;--accent:#57c7e3;--ok:#4ec97a;--warn:#f0b429;--bad:#ff6b6b}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
.wrap{max-width:760px;margin:0 auto;padding:28px 18px 120px}
h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--dim);font-size:14px;margin-bottom:20px}
.bar{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;color:var(--dim);
background:var(--card);border-radius:10px;padding:12px 14px;margin-bottom:22px}
.bar b{color:var(--ink)}
.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}
.card{background:var(--card);border-radius:12px;padding:16px 18px;margin-bottom:16px}
.q{font-size:17px;font-weight:600;margin:0 0 6px}
.meta{font-size:12px;color:var(--dim);margin-bottom:12px}
.pov{margin-top:10px}
.pov h3{font-size:12px;letter-spacing:.08em;text-transform:uppercase;
color:var(--dim);margin:0 0 8px}
label.opt{display:block;background:#0d1b26;border:1px solid #1d3140;border-radius:9px;
padding:10px 12px;margin-bottom:8px;cursor:pointer;font-size:14px}
label.opt:has(input:checked){border-color:var(--accent);background:#0f2431}
label.opt input{margin-right:8px}
.tagline{color:var(--dim);font-size:11px;text-transform:uppercase;
letter-spacing:.07em;display:block;margin-bottom:4px}
.actions{position:fixed;left:0;right:0;bottom:0;background:#081018;
border-top:1px solid #1b2c39;padding:14px 18px;display:flex;gap:12px;
justify-content:center;align-items:center;flex-wrap:wrap}
a.btn,button.btn{background:var(--accent);color:#06222d;border:0;border-radius:9px;
padding:12px 22px;font-size:15px;font-weight:650;text-decoration:none;cursor:pointer}
button.ghost{background:transparent;color:var(--dim);border:1px solid #263d4d}
.stop{background:#2a1a12;border:1px solid #6b3f1c;border-radius:10px;
padding:12px 14px;margin-bottom:18px;font-size:14px}
pre{white-space:pre-wrap;word-break:break-word;background:#08131b;padding:12px;
border-radius:9px;font-size:12px;color:var(--dim)}
</style></head><body><div class="wrap">

<h1>Approve week __WEEK__</h1>
<div class="sub">__COUNT__ video__PLURAL__ · cadence ceiling __CEILING__/week (deliberate)
· budget 20 minutes</div>

<div class="bar">
  <span>breaker <b class="__BRK_CLASS__">__BRK__</b></span>
  <span>validators <b class="__VAL_CLASS__">__VAL__</b></span>
  <span>inventory left <b>__INV__</b></span>
  <span>competition scoring <b class="warn">__SCORED__</b></span>
</div>

__STOPS__

<form id="f">__CARDS__</form>

<div class="card">
  <h3 style="margin:0 0 8px;font-size:13px;color:var(--dim)">If the button is blocked</h3>
  <p style="font-size:13px;color:var(--dim);margin:0 0 8px">Copy this and paste it
  into a new issue titled <code>APPROVE __WEEK__</code>, or run it on the Mac:
  <code>bin/loop-approve.sh __WEEK__</code></p>
  <pre id="raw"></pre>
</div>

</div>
<div class="actions">
  <button class="btn" id="go">Approve all __COUNT__ →</button>
  <button class="btn ghost" id="copy">Copy approval block</button>
</div>

<script>
const DATA = __DATA__;
const REPO = "__REPO__";

function body(){
  const lines = ["Approving the week as shown on the approval page.", ""];
  for (const it of DATA.items){
    const sel = document.querySelector(`input[name="pov-${it.slug}"]:checked`);
    lines.push(`- slug: ${it.slug} | pov: ${sel ? sel.value : "bank"}`);
  }
  lines.push("", `week: ${DATA.week}`, `queue_generated: ${DATA.generated}`,
             `validators_passed: ${DATA.validators_passed}`,
             "", "APPROVE ALL");
  return lines.join("\\n");
}
function refresh(){ document.getElementById("raw").textContent =
  `APPROVE ${DATA.week}\\n\\n` + body(); }
document.getElementById("f").addEventListener("change", refresh);
refresh();

document.getElementById("go").addEventListener("click", () => {
  const u = `https://github.com/${REPO}/issues/new?title=`
    + encodeURIComponent(`APPROVE ${DATA.week}`)
    + `&body=` + encodeURIComponent(body())
    + `&labels=loop-approval`;
  window.open(u, "_blank", "noopener");
});
document.getElementById("copy").addEventListener("click", async () => {
  await navigator.clipboard.writeText(`APPROVE ${DATA.week}\\n\\n` + body());
  document.getElementById("copy").textContent = "copied";
});
</script>
</body></html>
"""

CARD = """
<div class="card">
  <p class="q">__N__. __QUESTION__</p>
  <div class="meta">__SLUG__ · __SOURCES__ sources · __BEATS__ planned beats
   · POV __POVID__</div>
  <div class="pov">
    <h3>Is this her line?</h3>
    __OPTIONS__
  </div>
</div>
"""

OPTION = """<label class="opt"><input type="radio" name="pov-__SLUG__"
 value="__VALUE__"__CHECKED__><span class="tagline">__LABEL__</span>__TEXT__</label>"""


def build(queue: dict, topics: dict | None = None) -> Path:
    cfg = config()
    items = queue["items"]
    cards = []
    for i, it in enumerate(items, 1):
        opts = []
        bank_line = it.get("pov_bank_line", "")
        script_line = it.get("pov_script_line", "")
        # The bank line is the default: it is verbatim in her own words from the
        # interview. The script line is an editorial paraphrase, offered second.
        if bank_line:
            opts.append(OPTION
                        .replace("__SLUG__", it["slug"])
                        .replace("__VALUE__", "bank")
                        .replace("__CHECKED__", " checked")
                        .replace("__LABEL__", f"POV bank · {it.get('pov_id','')}"
                                              " · her interview, verbatim")
                        .replace("__TEXT__", html.escape(bank_line)))
        if script_line and script_line != bank_line:
            opts.append(OPTION
                        .replace("__SLUG__", it["slug"])
                        .replace("__VALUE__", "script")
                        .replace("__CHECKED__", "" if bank_line else " checked")
                        .replace("__LABEL__", "As currently written in the script"
                                              " · editorial paraphrase")
                        .replace("__TEXT__", html.escape(script_line)))
        if not opts:
            opts.append('<p class="bad">No POV line resolved — this row cannot '
                        'ship. See loop/state/stops/.</p>')
        cards.append(CARD
                     .replace("__N__", str(i))
                     .replace("__QUESTION__", html.escape(it["question"]))
                     .replace("__SLUG__", it["slug"])
                     .replace("__SOURCES__", str(it.get("source_count", "?")))
                     .replace("__BEATS__", str(it.get("planned_beats", "?")))
                     .replace("__POVID__", it.get("pov_id", "—"))
                     .replace("__OPTIONS__", "\n    ".join(opts)))

    brk = queue.get("breaker", "closed")
    val = "passed" if queue.get("validators_passed") else "FAILED"
    stops = ""
    if queue.get("unauthored"):
        stops += ('<div class="stop"><b>Named stop:</b> '
                  f'{len(queue["unauthored"])} slot(s) had no authored script. '
                  'Briefs are in <code>loop/briefs/</code>. The week still ships '
                  f'{len(items)}.</div>')
    gaps = [(it["slug"], it["attribution_gaps"]) for it in items
            if it.get("attribution_gaps")]
    if gaps:
        rows = "; ".join(f"{s} → {', '.join(g)}" for s, g in gaps)
        stops += ('<div class="stop"><b>Attribution gap (does not block):</b> '
                  'the narration names a body that is not in that script\'s '
                  f'<code>## Sources</code> list — {html.escape(rows)}. Nothing '
                  'unsourced can reach the screen either way; this is a '
                  'bibliography line, and it clears itself once added.</div>')
    if brk == "tripped":
        stops += ('<div class="stop"><b>Circuit breaker tripped.</b> Publishing '
                  'is halted. Drafting and rendering continue; approving here is '
                  'still useful, nothing will go public until the breaker is '
                  'reset.</div>')

    data = {"week": queue["week"], "generated": queue["generated"],
            "validators_passed": queue.get("validators_passed"),
            "items": [{"slug": it["slug"], "question": it["question"],
                       "pov_id": it.get("pov_id")} for it in items]}

    page = (TEMPLATE
            .replace("__WEEK__", queue["week"])
            .replace("__COUNT__", str(len(items)))
            .replace("__PLURAL__", "" if len(items) == 1 else "s")
            .replace("__CEILING__", str(cfg["cadence"]["videos_per_week"]))
            .replace("__BRK__", brk)
            .replace("__BRK_CLASS__", "ok" if brk == "closed" else "bad")
            .replace("__VAL__", val)
            .replace("__VAL_CLASS__", "ok" if val == "passed" else "bad")
            .replace("__INV__", str((topics or {}).get("inventory_remaining", "?")))
            .replace("__SCORED__",
                     "available" if (topics or {}).get("competition_scoring", {})
                     .get("available") else "unscored — named stop")
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
