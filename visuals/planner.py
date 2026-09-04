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
# The segment types that CARRY CONTENT, as opposed to the fillers (text_beat,
# ambient_drift). destagnate() reuses one of these as relief and the filler
# pass must never displace one. Module-level, not a local inside destagnate(),
# so a domain pack can add its own device renderers to the set — as a local it
# silently ignored every extension.
INFO = {"stat_card", "depth_descent", "comparison", "zone_column",
        "pressure_gauge", "light_attenuation", "world_map", "timeline",
        "anatomy_callout", "size_ladder"}

# The hero visual a cold open reaches for. Deep sea opens on a descent; a
# domain pack overrides this with its own structural device (materials opens
# on a thermal ascent). Hardcoding "depth_descent" here is what put two
# depth_descent beats and four light_attenuation beats into a plan for a
# script about welding arcs.
COLD_OPEN_SEGMENT = "depth_descent"

# ---------- signals ----------
SIGNALS = [
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

def classify(text, heading):
    """Ranked candidates, best first. Ranking is by signal strength, not order."""
    h = heading.lower()
    if "producer pov" in h or "[HUMAN]" in text: return ["quote_card"]
    if "title card" in h:                        return ["text_beat"]
    scored = []
    for name, pat in SIGNALS:
        hits = len(re.findall(pat, text, re.I))
        if hits: scored.append((hits, name))
    # a concrete measurement is a strong stat_card signal regardless of other matches
    if find_measures(text): scored.append((2, "stat_card"))
    if "cold open" in h:   scored.append((3, COLD_OPEN_SEGMENT))
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

# The ACTIVE domain's own directive pack, if it has one. Grafted by domain,
# never by the presence of a word: a deep-sea script writing {{thermal}} must
# not get a materials card, so design.DOMAIN decides and nothing else does.
try:
    import design as _design
    if _design.DOMAIN == "materials-and-manufacturing":
        import segments_materials as _mat
        _mat.install(sys.modules[__name__])
except Exception:
    pass

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

def plan(md_path):
    """Plan at SECTION level. A section gets a dominant visual; beats inside it
    alternate between that visual, typographic beats, and breathing room. This is
    how explainers actually work — a diagram holds while narration continues."""
    beats = parse(open(md_path).read())
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
        for cand in classify(joined, h):
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
    return destagnate(out)


MAX_RUN = 2   # never show the same segment type more than twice in a row

def destagnate(plan):
    """No visual treatment may persist past MAX_RUN consecutive beats. Prefer the
    nearest informational visual in the same section; otherwise breathe."""
    global INFO
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
