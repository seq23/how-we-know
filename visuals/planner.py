"""Script -> visual plan.

Reads a narration script, splits it into beats, and assigns each beat a segment
type with arguments EXTRACTED FROM THE TEXT. The planner never invents a number,
a place, or a date: if it cannot find the value in the script, it does not emit a
segment that would display one.
"""
import re, json, sys, os


WPM = 145
MIN_BEAT, MAX_BEAT = 3.5, 9.0      # seconds of narration per visual
NO_REPEAT_WINDOW = 3               # a segment type may not recur within N beats

# ---------- extraction ----------
NUM = r"[\d][\d,]*(?:\.\d+)?"

def find_measures(s):
    """(value, unit) pairs actually present in the sentence."""
    pat = rf"({NUM})\s*(meters?|metres?|m\b|feet|ft\b|kilometers?|kilometres?|km\b|degrees?|percent|%|times|atmospheres?)"
    return [(m.group(1), m.group(2)) for m in re.finditer(pat, s, re.I)]

def find_years(s):
    return re.findall(r"\b(1[5-9]\d\d|20[0-2]\d)\b", s)

def find_places(s):
    known = ["Mariana Trench","Challenger Deep","Pacific Ocean","Atlantic Ocean",
             "Indian Ocean","Gulf of Mexico","Puerto Rico Trench","Tonga Trench",
             "Monterey Canyon","Antarctica","Japan","Hawaii"]
    return [k for k in known if k.lower() in s.lower()]

# ---------- signals ----------
DEEP_SEA_SIGNALS = [
    ("pressure_gauge",   r"\bpressure\b|\batmospher|\bcrush|\bpsi\b|\bbar\b"),
    ("light_attenuation",r"\bwavelength|\bred light|\bcolou?r .*absorb|\bsunlight (?:is )?absent|\blight (?:dies|fades|disappears)|\bphotic\b"),
    ("zone_column",      r"\bzone\b|\bmidnight\b|\btwilight\b|\bhadal\b|\babyssal\b|\bbathypelagic\b|\bwater column\b"),
    ("world_map",        r"\btrench\b|\bocean\b.*\b(?:western|eastern|southern|northern)\b|\blocated\b|\bregion\b"),
    ("timeline",         r"\b(?:1[5-9]\d\d|20[0-2]\d)\b.*\b(?:1[5-9]\d\d|20[0-2]\d)\b|\bhistory\b|\bfirst\b.*\bdescent\b|\bexpedition\b"),
    ("anatomy_callout",  r"\bteeth\b|\bjaw|\beyes?\b|\bfins?\b|\bbody\b|\borgan|\btissue|\btentacle|\blure\b"),
    ("size_ladder",      r"\blength\b|\blong\b|\bsize\b|\bmetres? long\b|\bcompared? (?:to|with) a\b"),
    ("comparison",       r"\bEverest\b|\btaller than\b|\bdeeper than\b|\bcompare|\bversus\b|\bthan the height\b"),
    ("depth_descent",    r"\bdescend|\bdive\b|\bdeeper\b|\bbelow (?:mean )?sea level\b|\bdown to\b"),
    ("stat_card",        rf"\b{NUM}\s*(?:meters?|metres?|feet|kilometers?|percent|%|times)"),
]

# THE SAME LIST IS WRONG FOR A DOMAIN THAT IS NOT THE OCEAN. The directives
# {{thermal}} and {{stages}} were already parsed, so a materials script got its
# device cards wherever it asked for them explicitly - but the HEURISTICS above
# still ran on every other beat, and they are deep sea's. "how-hot-does-a-
# welding-arc-get" planned two `depth_descent` beats and four
# `light_attenuation` beats off the words "deeper" and "down to": the ocean's
# "light dies with depth" card, in an episode whose whole device is the
# physical inverse. Ranking materials higher would not have fixed it; the
# ocean entries have to be ABSENT, or they win any sentence that happens not
# to mention heat.
#
# Kept because they are already domain-agnostic: stat_card, comparison,
# size_ladder, timeline. Dropped: light_attenuation, depth_descent,
# pressure_gauge (its args are a depth in metres), zone_column (this domain's
# counterpart is process_column), world_map (find_places is a hardcoded list
# of ocean trenches), anatomy_callout (species anatomy).
MATERIALS_SIGNALS = [
    ("thermal_ascent",  r"\bdegrees?\b|\bcelsius\b|\bkelvin\b|\bmelt|\bmolten\b"
                        r"|\bforge|\banneal|\btemper(?:ing|ed)?\b|\bquench"
                        r"|\bfurnace\b|\bkiln\b|\bplasma\b|\barc\b|\bheat(?:ed|ing)?\b"
                        r"|\bincandescen|\bthermal\b|\bsinter"),
    ("process_column",  r"\bstage\b|\bstages\b|\bstep\b|\bprocess\b|\bproduction line\b"
                        r"|\bmanufactur|\bfabricat|\bthe sequence\b"),
    ("size_ladder",     r"\bstrength\b|\bstrong(?:er|est)?\b|\bmodulus\b|\bstiff"
                        r"|\bgigapascal|\bmegapascal|\btensile\b|\bhardness\b"),
    ("comparison",      r"\bcompared? (?:to|with)\b|\bversus\b|\bstronger than\b"
                        r"|\bhotter than\b|\btimes (?:the|as)\b"),
    ("timeline",        r"\b(?:1[5-9]\d\d|20[0-2]\d)\b.*\b(?:1[5-9]\d\d|20[0-2]\d)\b"
                        r"|\bhistory\b|\bfirst (?:produced|made|synthesi)"),
    ("stat_card",       rf"\b{NUM}\s*(?:degrees?|percent|%|times|gigapascals?|megapascals?"
                        rf"|GPa|MPa|nanometres?|nanometers?|microns?|micrometres?)"),
]

# FOOD (2026-11-01). Its device is the kitchen scale (visuals/domains.py
# DEVICES["food-science"]: a temperature axis), drawn by the same
# segments_materials renderers, which read the ACTIVE domain's device. Only
# domain-agnostic or temperature signals: the ocean's entries must be ABSENT
# for the same reason as materials' above.
FOOD_SIGNALS = [
    ("thermal_ascent",  r"\bdegrees?\b|\bcelsius\b|\bfahrenheit\b|\boven\b|\bbak(?:e|ed|ing)\b"
                        r"|\bsear(?:ed|ing)?\b|\bboil(?:s|ed|ing)?\b|\broast"),
    ("process_column",  r"\bstage\b|\bstages\b|\bstep\b|\bprocess\b|\bthe sequence\b"),
    ("comparison",      r"\bcompared? (?:to|with)\b|\bversus\b|\btimes (?:the|as)\b"),
    ("timeline",        r"\b(?:1[5-9]\d\d|20[0-2]\d)\b.*\b(?:1[5-9]\d\d|20[0-2]\d)\b|\bhistory\b"),
    ("stat_card",       rf"\b{NUM}\s*(?:degrees?|percent|%|times|grams?|minutes?)"),
]

# THE SCRIPT'S OWN DOMAIN decides, per call - never the process environment.
#
# CONFIRMED 2026-11-01 (the owner's screenshot of the rice Short): until this
# date the signal table was picked ONCE, at import, from visuals/design.py's
# HWK_DOMAIN, defaulting to deep sea, and bin/batch-session.sh's "build any
# missing shot plan" step runs the planner WITHOUT HWK_DOMAIN (only the render
# step sets it). So every non-ocean script was planned with the ocean's
# signals and the ocean's cold open: why-does-rice-get-sticky got two
# `depth_descent` beats with empty args, which assemble.py then drew with
# their defaults - "CHALLENGER DEEP ... METRES" - on a food episode. Four
# materials plans carry the same defect (depth_descent, light_attenuation,
# zone_column, anatomy_callout). And food-science had no row here at all, so
# even with HWK_DOMAIN set it fell back to the ocean. Now: the script's
# **Domain:** line (loop/domains.py's convention; no line = the channel's
# first domain, deep sea), an undeclared domain raises, and
# visuals/plan_domain.py refuses any plan that still carries another
# domain's graphics (assemble.py, the batch and validator V77).
_SIGNALS_BY_DOMAIN = {
    "deep-sea-ocean-science": (DEEP_SEA_SIGNALS, "depth_descent"),
    "materials-and-manufacturing": (MATERIALS_SIGNALS, "thermal_ascent"),
    "food-science": (FOOD_SIGNALS, "thermal_ascent"),
}
DEFAULT_DOMAIN = "deep-sea-ocean-science"
_DOMAIN_LINE = re.compile(r"^\*\*Domain:\*\*\s*([a-z0-9-]+)", re.M)


def script_domain(md):
    """The domain a script declares, or the channel's first domain."""
    m = _DOMAIN_LINE.search(md or "")
    return m.group(1) if m else DEFAULT_DOMAIN


def signals_for(domain):
    """(signals, cold-open segment) for a domain; KeyError names the gap."""
    try:
        return _SIGNALS_BY_DOMAIN[domain]
    except KeyError:
        raise KeyError(f"planner has no signal table for domain {domain!r}: "
                       f"add one to visuals/planner.py _SIGNALS_BY_DOMAIN "
                       f"rather than plan it with another domain's graphics") from None


# Kept for callers that read the module defaults; plan() never uses them.
SIGNALS, COLD_OPEN_SEGMENT = DEEP_SEA_SIGNALS, "depth_descent"

def classify(text, heading, signals=None, cold_open=None):
    """Ranked candidates, best first. Ranking is by signal strength, not order."""
    signals = DEEP_SEA_SIGNALS if signals is None else signals
    cold_open = cold_open or "depth_descent"
    h = heading.lower()
    if "producer pov" in h or "[HUMAN]" in text: return ["quote_card"]
    if "title card" in h:                        return ["text_beat"]
    scored = []
    for name, pat in signals:
        hits = len(re.findall(pat, text, re.I))
        if hits: scored.append((hits, name))
    # a concrete measurement is a strong stat_card signal regardless of other matches
    if find_measures(text): scored.append((2, "stat_card"))
    if "cold open" in h:   scored.append((3, cold_open))
    scored.sort(key=lambda x: -x[0])
    ranked = []
    for _, n in scored:
        if n not in ranked: ranked.append(n)
    ranked.append("text_beat")
    return ranked

# ---------- directives ----------
DIRECTIVE = re.compile(r"^\{\{\s*(\w+)\s*:?\s*(.*?)\s*\}\}$")

def parse_directive(line):
    m = DIRECTIVE.match(line.strip())
    if not m: return None
    kind, raw = m.group(1).lower(), m.group(2)
    parts = [p.strip() for p in raw.split("|")] if raw else []
    try:
        if kind == "stat":
            if not parts or not parts[0]: return None
            return ("stat_card", {"value": parts[0],
                                  "unit": parts[1] if len(parts)>1 else "",
                                  "caption": parts[2] if len(parts)>2 else "",
                                  "source": parts[3] if len(parts)>3 else ""})
        if kind == "descent":
            return ("depth_descent", {"to_depth": int(float(parts[0].replace(",",""))),
                                      "label": parts[1] if len(parts)>1 else ""})
        if kind == "compare":
            if len(parts) != 2: return None
            (an,av),(bn,bv) = [p.split("=") for p in parts]
            return ("comparison", {"a_label":an.strip().upper(),"a_m":int(float(av)),
                                   "b_label":bn.strip().upper(),"b_m":int(float(bv))})
        if kind == "zones":
            return ("zone_column", {"highlight": parts[0].upper() if parts and parts[0] else None})
        if kind == "pressure":
            return ("pressure_gauge", {"depth_m": int(float(parts[0].replace(",","")))})
        if kind == "light":
            return ("light_attenuation", {})
        if kind == "thermal":
            # materials-and-manufacturing's structural device — the thermal-
            # scale analogue of {{descent}}. visuals/segments_materials.py.
            if not parts or not parts[0]: return None
            return ("thermal_ascent", {"to_temp": int(float(parts[0].replace(",",""))),
                                       "label": parts[1] if len(parts) > 1 else ""})
        if kind == "stages":
            # materials' analogue of {{zones}}.
            return ("process_column", {"highlight": parts[0].upper() if parts and parts[0] else None})
        if kind == "map":
            pts=[]
            for p in parts:
                nm,_,co = p.partition("@")
                lon,_,lat = co.partition(",")
                pts.append((nm.strip(), float(lon), float(lat)))
            return ("world_map", {"points": pts[:3]}) if pts else None
        if kind == "timeline":
            ev=[]
            for p in parts:
                y,_,lab = p.partition("=")
                ev.append((int(y.strip()), lab.strip()))
            return ("timeline", {"events": ev[:6]}) if len(ev)>=2 else None
        if kind == "anatomy":
            if not parts: return None
            pr=[]
            for p in parts[1:]:
                lab,_,co = p.partition("@")
                x,_,y = co.partition(",")
                pr.append((lab.strip(), float(x), float(y)))
            return ("anatomy_callout", {"title": parts[0], "parts": pr})
        if kind == "ladder":
            it=[]
            for p in parts:
                nm,_,v = p.partition("=")
                it.append((nm.strip(), float(v)))
            return ("size_ladder", {"items": it[:6]}) if len(it)>=2 else None
        if kind == "quote":   return ("quote_card", None)      # filled from beat
        if kind == "text":    return ("text_beat", None)
        if kind == "ambient": return ("ambient_drift", None)
    except Exception:
        return None      # malformed -> ignore, fall back to heuristics
    return None

# The extended pack wraps parse_directive, so it must load AFTER the base
# definition above exists. Importing it at the top of the module silently
# produced a no-op graft and left every v2 directive unparsed.
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import segments_ext2 as _ext2
    _ext2.install(sys.modules[__name__])
    import segments_species as _sp
    _sp.install(sys.modules[__name__])
except Exception:
    _ext2 = None

# ---------- parsing ----------
def parse(md):
    body = md.split("## Narration",1)[-1].split("\n## ",1)[0]
    beats, heading, pending = [], "", None
    for block in re.split(r"\n\s*\n", body):
        b = block.strip()
        if not b: continue
        if b.startswith("###"):
            heading = b.lstrip("#").strip(); pending = None; continue
        if b.startswith("#"): continue
        lines = b.split("\n")
        directive = None
        while lines and DIRECTIVE.match(lines[0].strip()):
            directive = parse_directive(lines.pop(0))
        prose = " ".join(l for l in lines if not DIRECTIVE.match(l.strip())).strip()
        if not prose: continue
        idx = 0
        for sent in split_sentences(prose):
            if len(sent.split()) >= 5:
                beats.append({"heading": heading, "text": sent,
                              "directive": directive, "para_idx": idx})
                idx += 1
    return beats

def split_sentences(p):
    p = p.replace("[HUMAN]", "").strip()
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z'\"])", p)
    out, buf = [], ""
    for s in parts:                      # merge very short sentences forward
        buf = (buf + " " + s).strip() if buf else s
        if len(buf.split()) >= 12:
            out.append(buf); buf = ""
    if buf: out.append(buf) if not out else out.__setitem__(-1, out[-1] + " " + buf)
    return out

def dur(text):
    return max(MIN_BEAT, min(MAX_BEAT, len(text.split()) / WPM * 60))

# ---------- planning ----------
def build_args(seg, beat):
    t = beat["text"]
    if seg == "thermal_ascent":
        # Only with a cited figure. A thermal card with an invented temperature
        # would be exactly the "no invented figures" rule broken by a heuristic.
        m = re.search(rf"({NUM})\s*degrees?", t, re.I)
        if not m:
            return None
        return {"to_temp": int(float(m.group(1).replace(",", ""))), "label": None}
    if seg == "process_column":
        return {"highlight": None}
    if seg == "stat_card":
        ms = find_measures(t)
        if not ms: return None
        v,u = ms[0]
        return {"value": v, "unit": u.upper().rstrip("."), "caption": "", "source": ""}
    if seg == "pressure_gauge":
        ms = [m for m in find_measures(t) if m[1].lower().startswith(("m","met","f","k"))]
        if not ms: return None
        v = float(ms[0][0].replace(",",""))
        return {"depth_m": int(v)}
    if seg == "world_map":
        pl = find_places(t)
        if not pl: return None
        return {"points": [(p, 142.2, 11.3) if "Challenger" in p or "Mariana" in p else (p, 0, 0) for p in pl][:3]}
    if seg == "timeline":
        ys = find_years(t)
        if len(ys) < 2: return None
        return {"events": [(int(y), "") for y in sorted(set(ys))][:6]}
    if seg == "quote_card":
        return {"text": t, "attrib": ""}
    if seg == "text_beat":
        return {"lines": wrap_lines(t)}
    if seg == "comparison":
        return {} if re.search(r"Everest", t, re.I) else None
    if seg in ("zone_column","depth_descent","light_attenuation","ambient_drift",
               "anatomy_callout","size_ladder"):
        return {}
    return {}

DANGLING = {"the","a","an","of","to","in","on","at","for","with","from","and","or",
            "that","this","its","but","as","by","into","onto","than","then","so",
            "is","are","was","were","be","been","can","could","will","would","may",
            "might","must","not","no","if","when","where","which","who","whose",
            # adjectives/determiners that leave the reader waiting for a noun
            "deepest","largest","smallest","biggest","greatest","longest","highest",
            "most","more","less","very","such","other","another","same","own",
            "both","each","every","many","few","several","certain","entire","whole"}

def key_phrase(t, max_words=10):
    """A short, grammatical phrase. Never splits a number, never truncates a word,
    never ends on a dangling function word or a half-finished proper name."""
    t = re.sub(r"\s+", " ", t).strip()
    clauses = [c.strip() for c in re.split(r";|\s-\s|\u2014", t) if c.strip()]
    best = None
    for c in clauses:
        if len(c.split()) < 3: continue
        has_num = bool(re.search(r"\d", c))
        if best is None or (has_num and not re.search(r"\d", best)): best = c
        if has_num: break
    best = (best or t).rstrip(" .,;:")
    w = best.split()
    if len(w) <= max_words:
        return " ".join(w).rstrip(",")

    cut = w[:max_words]
    # never end mid-proper-noun: if the next word continues a capitalised run,
    # either take it or drop back before the run started.
    def cap(x): return x[:1].isupper() and not x.isupper()
    while len(cut) < len(w) and cap(cut[-1]) and cap(w[len(cut)]) and len(cut) < max_words + 2:
        cut.append(w[len(cut)])                 # complete the name
    if len(cut) < len(w) and cap(cut[-1]) and cap(w[len(cut)]):
        while cut and cap(cut[-1]): cut.pop()   # still mid-name: drop the whole run
    while cut and cut[-1].lower().strip(",") in DANGLING:
        cut.pop()
    return " ".join(cut).rstrip(",") if cut else " ".join(w[:max_words])

def wrap_lines(t, per=4):
    w = key_phrase(t).split()
    return [" ".join(w[i:i+per]) for i in range(0, len(w), per)]

def dur(text):
    return max(MIN_BEAT, min(MAX_BEAT, len(text.split()) / WPM * 60))

# ---------- planning ----------
def build_args(seg, beat):
    t = beat["text"]
    if seg == "thermal_ascent":
        # Only with a cited figure. A thermal card with an invented temperature
        # would be exactly the "no invented figures" rule broken by a heuristic.
        m = re.search(rf"({NUM})\s*degrees?", t, re.I)
        if not m:
            return None
        return {"to_temp": int(float(m.group(1).replace(",", ""))), "label": None}
    if seg == "process_column":
        return {"highlight": None}
    if seg == "stat_card":
        ms = find_measures(t)
        if not ms: return None
        v,u = ms[0]
        return {"value": v, "unit": u.upper().rstrip("."), "caption": "", "source": ""}
    if seg == "pressure_gauge":
        ms = [m for m in find_measures(t) if m[1].lower().startswith(("m","met","f","k"))]
        if not ms: return None
        v = float(ms[0][0].replace(",",""))
        return {"depth_m": int(v)}
    if seg == "world_map":
        pl = find_places(t)
        if not pl: return None
        return {"points": [(p, 142.2, 11.3) if "Challenger" in p or "Mariana" in p else (p, 0, 0) for p in pl][:3]}
    if seg == "timeline":
        ys = find_years(t)
        if len(ys) < 2: return None
        return {"events": [(int(y), "") for y in sorted(set(ys))][:6]}
    if seg == "quote_card":
        return {"text": t, "attrib": ""}
    if seg == "text_beat":
        return {"lines": wrap_lines(t)}
    if seg == "comparison":
        return {} if re.search(r"Everest", t, re.I) else None
    if seg in ("zone_column","depth_descent","light_attenuation","ambient_drift",
               "anatomy_callout","size_ladder"):
        return {}
    return {}

def plan(md_path, domain=None):
    """Plan at SECTION level. A section gets a dominant visual; beats inside it
    alternate between that visual, typographic beats, and breathing room. This is
    how explainers actually work — a diagram holds while narration continues.

    `domain` defaults to the script's own **Domain:** line (see signals_for)."""
    md = open(md_path).read()
    signals, cold_open = signals_for(domain or script_domain(md))
    beats = parse(md)
    sections, order = {}, []
    for b in beats:
        h = b["heading"] or "_"
        if h not in sections: sections[h] = []; order.append(h)
        sections[h].append(b)

    out, recent_heroes, amb = [], [], 0
    for h in order:
        group = sections[h]
        joined = " ".join(g["text"] for g in group)
        # rank using the whole section: far more signal than one sentence
        hero, hero_args = None, None
        for cand in classify(joined, h, signals, cold_open):
            if cand in ("text_beat",): continue
            if cand in recent_heroes[-2:]: continue
            for g in group:                       # find a beat that can populate it
                a = build_args(cand, g)
                if a is not None:
                    hero, hero_args, hero_beat = cand, a, g; break
            if hero: break
        if hero: recent_heroes.append(hero)

        for i, b in enumerate(group):
            hl = h.lower()
            d = b.get("directive")
            if d and b.get("para_idx", 0) % 2 == 1 and d[0] not in (
                    "quote_card","text_beat","ambient_drift"):
                out.append({"segment":"text_beat","seconds":round(dur(b["text"]),2),
                            "heading":h,"narration":b["text"],
                            "args":{"lines":wrap_lines(b["text"])},
                            "from":"directive-rhythm"}); continue
            if d:                                  # explicit direction wins
                seg, args = d
                if args is None:                   # quote/text/ambient take beat data
                    if seg == "quote_card":  args = {"text": b["text"], "attrib": ""}
                    elif seg == "text_beat": args = {"lines": wrap_lines(b["text"])}
                    else: args = {"variant": amb % 5}; amb += 1
                out.append({"segment": seg, "seconds": round(dur(b["text"]),2),
                            "heading": h, "narration": b["text"], "args": args,
                            "from": "directive"})
                continue
            if "producer pov" in hl or "[HUMAN]" in b["text"]:
                out.append({"segment":"quote_card","seconds":round(dur(b["text"]),2),
                            "heading":h,"narration":b["text"],
                            "args":{"text":b["text"],"attrib":""},
                            "from":"heading"}); continue
            if "title card" in hl:
                out.append({"segment":"text_beat","seconds":round(dur(b["text"]),2),
                            "heading":h,"narration":b["text"],
                            "args":{"lines":wrap_lines(b["text"])},
                            "from":"heading"}); continue
            if hero and i == 0:
                seg, args = hero, hero_args
            elif hero and i % 3 == 2:             # return to the hero visual
                seg, args = hero, hero_args
            elif i % 3 == 1:
                seg, args = "text_beat", {"lines": wrap_lines(b["text"])}
            else:
                seg, args = "ambient_drift", {"variant": amb % 5}; amb += 1
            out.append({"segment": seg, "seconds": round(dur(b["text"]),2),
                        "heading": h, "narration": b["text"], "args": args,
                        "from": "heuristic"})
    slug = os.path.splitext(os.path.basename(md_path))[0]
    return picture_pass(destagnate(out), md, domain or script_domain(md), slug)


MAX_RUN = 2   # never show the same segment type more than twice in a row

def destagnate(plan):
    """No visual treatment may persist past MAX_RUN consecutive beats. Prefer the
    nearest informational visual in the same section; otherwise breathe."""
    INFO = {"stat_card","depth_descent","comparison","zone_column","pressure_gauge",
            "light_attenuation","world_map","timeline","anatomy_callout","size_ladder",
            "thermal_ascent","process_column"}
    # nearest informational beat per section, to reuse as relief
    hero = {}
    for b in plan:
        if b["segment"] in INFO and b["heading"] not in hero:
            hero[b["heading"]] = (b["segment"], b["args"])
    run, prev, amb = 0, None, 0
    for b in plan:
        if b["segment"] == prev:
            run += 1
        else:
            run, prev = 1, b["segment"]
        if run > MAX_RUN:
            h = hero.get(b["heading"])
            if h and h[0] != b["segment"]:                 # best relief: real content
                b["segment"], b["args"] = h[0], h[1]
            elif b["segment"] != "text_beat":              # never relieve X with X
                b["segment"], b["args"] = "text_beat", {"lines": wrap_lines(b["narration"])}
            else:
                b["segment"], b["args"] = "ambient_drift", {"variant": amb % 5}; amb += 1
            b["from"] = b.get("from","") + "+destagnate"
            run, prev = 1, b["segment"]
    return plan

if __name__ == "__main__":
    p = plan(sys.argv[1])
    total = sum(s["seconds"] for s in p)
    from collections import Counter
    print(f"{len(p)} beats · {total/60:.1f} min · avg {total/len(p):.1f}s\n")
    for k,v in Counter(s["segment"] for s in p).most_common():
        print(f"  {k:<20} {v}")
    print()
    for s in p[:12]:
        print(f"{s['seconds']:>5.1f}s  {s['segment']:<18} {s['narration'][:62]}")
    json.dump(p, open(sys.argv[2],"w"), indent=2) if len(sys.argv)>2 else None


# ---------------------------------------------------------------------------
# THE PLAN THE AUDIO IS INDEXED AGAINST.
#
# assemble.py reads plans/<slug>.json and takes audio/<slug>/NNNN.wav by plan
# position. voice/narrate_all.py used to plan from the SCRIPT every night, so
# an episode whose script had moved on from its rendered plan - episode 13,
# 62 beats by script, 61 in the plan that aired - had one beat the narrator
# generated every night and bin/batch-session.sh moved aside as an orphan
# every night, for ever: a wasted beat (2-25 minutes on an 8 GB M2) and a
# permanent "41/42 complete". One plan, one index: when a plan file exists it
# is the authority, because it is what the render will use; the script is the
# source only until that file is written.
PLANS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "plans")
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")


def plan_for_audio(slug, plans_dir=None, scripts_dir=None):
    """(plan, source) - plans/<slug>.json when it exists, else planned from
    the script. `source` is "plan" or "script" so a caller can say which."""
    pf = os.path.join(plans_dir or PLANS_DIR, f"{slug}.json")
    if os.path.exists(pf):
        with open(pf) as f:
            return json.load(f), "plan"
    return plan(os.path.join(scripts_dir or SCRIPTS_DIR, f"{slug}.md")), "script"


# ---------------------------------------------------------------------------
# PICTURES FIRST (hostile review, 2026-11-02; owner: "We need to optimize
# everything for viewers").
#
# CONFIRMED: 55-68% of every video's shots were typographic cards repeating the
# narration word for word, and "What does a goblin shark look like?" was
# planned with no picture of the shark at all. The median viewer left at about
# 1:46. So, on top of the section planning above, and WITHOUT changing a beat's
# count, order or narration (the audio is indexed by beat position):
#
#   * a picture on screen within FIRST_PICTURE_S of the start;
#   * never more than MAX_GAP_S without one;
#   * typographic cards at most TEXT_MAX_SHARE of the running time, and a
#     text_beat never repeats the narration: the heuristic/rhythm text_beat
#     becomes a picture, and a title card shows the episode's question;
#   * a "what does X look like" episode shows X in at least LOOK_LIKE_SHARE of
#     its shots (verified public-domain records, visuals/segments_species.py);
#   * anywhere else, a beat whose narration names exactly one covered animal
#     may show it (segments_species.heuristic_beat - never a lookalike).
#
# A "picture" is a species_image (a verified still or NOAA footage of the
# animal) or an ambient_drift beat, which visuals/footage.assign fills with the
# episode's own licence-checked footage. Whether a render really carried
# pictures is measured on the render by loop/render_gate.py's picture floor.
# Length is never padded with words or cards: the 10-minute floor is met by
# narration and pictures (owner, 2 Nov: aim for about 15 minutes).

PICTURE_SEGMENTS = {"species_image", "ambient_drift", "material_image"}
TEXT_CARDS = {"text_beat", "definition_card", "checklist_reveal", "contrast_pair"}
FIRST_PICTURE_S = 5.0
MAX_GAP_S = 15.0
TEXT_MAX_SHARE = 0.25
LOOK_LIKE_SHARE = 0.30
_LOOK_LIKE = re.compile(r"\blooks? like\b|\blook (?:so )?(?:weird|strange)\b", re.I)


def _title(md):
    m = re.search(r"^# (.+)$", md or "", re.M)
    return m.group(1).strip() if m else ""


def _species():
    try:
        import segments_species as SPX
        SPX.index()
        return SPX
    except Exception:
        return None


def look_like_subject(md, SPX=None):
    """The species key a "what does X look like" title asks about, or None."""
    SPX = SPX or _species()
    t = _title(md)
    if not SPX or not _LOOK_LIKE.search(t):
        return None
    hits = [h for h in SPX.match_subjects(t) if SPX.available(h[0])]
    return hits[0][0] if len(hits) == 1 else None


def is_picture(b):
    return b["segment"] in PICTURE_SEGMENTS


def _locked(b):
    """Beats this pass never repaints: her own POV quote."""
    return b["segment"] == "quote_card" or "[HUMAN]" in b.get("narration", "")


def picture_pass(plan, md, domain, slug="", SPX=None):
    SPX = SPX if SPX is not None else (_species() if domain == DEFAULT_DOMAIN else None)
    subject = look_like_subject(md, SPX) if SPX else None
    picks = {}

    def species_args(key, label=""):
        n = picks.get(key, 0)
        picks[key] = n + 1
        return {"subject": key, "label": label, "pick": n,
                "zoom": (1.0, 1.15, 1.3)[n % 3]}

    def to_picture(b, prefer=None):
        hit = None
        if SPX:
            names = [h for h in SPX.match_subjects(b["narration"]) if SPX.available(h[0])]
            if subject and any(k == subject for k, _ in names):
                hit = (subject, next(f for k, f in names if k == subject))
            elif len(names) == 1:
                hit = names[0]
            elif prefer:
                hit = (prefer, "")
        if hit:
            b["segment"], b["args"] = "species_image", species_args(*hit)
        else:
            b["segment"], b["args"] = "ambient_drift", {"variant": len(picks) % 5}
        b["from"] = b.get("from", "") + "+picture"

    # 1. the narration's own text never becomes the on-screen text
    title = _title(md)
    for b in plan:
        if _locked(b) or b["segment"] != "text_beat":
            continue
        if "title card" in (b.get("heading") or "").lower() and title:
            b["args"] = {"lines": wrap_lines(title)}
        else:
            to_picture(b)
    # 2. a beat that names one covered animal shows it
    if SPX:
        for b in plan:
            if not _locked(b) and b["segment"] in TEXT_CARDS | {"ambient_drift"}:
                names = [h for h in SPX.match_subjects(b["narration"]) if SPX.available(h[0])]
                if len(names) == 1 or (subject and any(k == subject for k, _ in names)):
                    to_picture(b)
    # 3. typographic cards capped by running time
    total = sum(b["seconds"] for b in plan) or 1.0
    text = [b for b in plan if b["segment"] in TEXT_CARDS and not _locked(b)]
    over = sum(b["seconds"] for b in text) - TEXT_MAX_SHARE * total
    for b in text[1::2] + text[0::2]:
        if over <= 0:
            break
        if "title card" in (b.get("heading") or "").lower():
            continue
        over -= b["seconds"]
        to_picture(b)
    # 4. a look-like episode shows its animal in >= LOOK_LIKE_SHARE of shots
    if subject:
        need = -(-int(LOOK_LIKE_SHARE * 100) * len(plan) // 100)
        have = sum(1 for b in plan if b["segment"] == "species_image"
                   and b["args"].get("subject") == subject)
        order = ([b for b in plan if b["segment"] == "ambient_drift"]
                 + [b for b in plan if b["segment"] in TEXT_CARDS]
                 + [b for b in plan if not is_picture(b) and b["segment"] not in TEXT_CARDS])
        for b in order:
            if have >= need:
                break
            if _locked(b) or (b["segment"] == "species_image"):
                continue
            b["segment"], b["args"] = "species_image", species_args(subject)
            b["from"] = b.get("from", "") + "+look-like"
            have += 1
    # 5. cadence: a picture within FIRST_PICTURE_S, then never a gap > MAX_GAP_S
    t, run = 0.0, 0.0          # run: seconds since the last picture, quotes excluded
    for i, b in enumerate(plan):
        end = t + b["seconds"]
        if not is_picture(b) and not _locked(b):
            if (i == 0 and t < FIRST_PICTURE_S) or run + b["seconds"] > MAX_GAP_S:
                to_picture(b)
        if is_picture(b):
            run = 0.0
        elif not _locked(b):
            run += b["seconds"]
        t = end
    return plan


def picture_report(plan):
    """(first picture start s, longest gap s, text-card share, by-subject shares)."""
    # Time on her own POV quote is not counted as a gap: those beats are her
    # interview lines, shown as she said them, and never repainted.
    t, first, run, gap = 0.0, None, 0.0, 0.0
    for b in plan:
        if is_picture(b):
            first = t if first is None else first
            gap, run = max(gap, run), 0.0
        elif not _locked(b):
            run += b["seconds"]
        t += b["seconds"]
    gap = max(gap, run)
    total = t or 1.0
    text = sum(b["seconds"] for b in plan if b["segment"] in TEXT_CARDS) / total
    subj = {}
    for b in plan:
        if b["segment"] == "species_image":
            k = b["args"].get("subject")
            subj[k] = subj.get(k, 0) + 1
    return {"first_picture_s": first, "max_gap_s": round(gap, 2),
            "text_share": round(text, 3),
            "subject_share": {k: round(v / len(plan), 3) for k, v in subj.items()}}
