"""Filter and cluster mined queries against the approved taxonomy.

Nothing is invented. Every surviving row is a real autocomplete string; this only
removes what is off-topic or barred, and groups what remains.
"""
import json, re, sys
from collections import defaultdict

tax = json.load(open("../pov/topic-taxonomy.json"))

# Off-topic noise that shares vocabulary with the niche.
NOISE = [
 r"\bbee gees\b", r"how deep is your love", r"\block\b.*\bocean\b.*\bsong\b",
 r"\blyrics?\b", r"\bsong\b", r"\bmovie\b", r"\bfilm\b", r"\btrailer\b",
 r"\bminecraft\b", r"\broblox\b", r"\bsubnautica\b", r"\bgame\b", r"\bmod\b",
 r"\bfortnite\b", r"\banime\b", r"\bmeme\b", r"\btiktok\b", r"\bedit\b",
 r"\bnear me\b", r"\bfor sale\b", r"\brecipe\b", r"\bstock\b", r"\bcrypto\b",
]
# Barred by the taxonomy's own exclusions.
BARRED = [
 r"\bconspiracy\b", r"\bmegalodon (?:is )?alive\b", r"\bmermaid", r"\bcryptid\b",
 r"\bbermuda triangle\b", r"\balien", r"\bufo\b", r"\bnessie\b", r"\bloch ness\b",
 r"\bcure\b", r"\bsupplement", r"\bdiet\b", r"\bstock market\b",
 # Financial-advice exclusion. Was r"\binvest", which is a prefix and therefore
 # also matched "investigation": it barred all 270 "air crash investigation"
 # queries across the broad mining pass and made incident-analysis look like the
 # single riskiest candidate domain (36% exclusion rate) when its real rate is
 # under 1%. Anchored to the actual money words instead.
 r"\binvest(?:s|ed|ing|ment|ments|or|ors)\b", r"\binvest in\b",
 r"\bdied\b.*\bvideo\b", r"\bgore\b", r"\bdeath video\b",
]
# Domain buckets, ordered: first match wins.
DOMAINS = [
 ("deep-sea-biology", r"creature|fish|squid|octopus|shark|crab|jelly|anglerfish|isopod|worm|coral|animal|species|eel|whale"),
 ("depth-and-zones",  r"\bdeep\b|depth|zone|trench|challenger|mariana|hadal|abyss|midnight|twilight|bottom|floor"),
 ("light-and-vision", r"biolumin|glow|light|dark|colou?r|see|eye|vision|transparent|invisible"),
 ("pressure-physics", r"pressure|crush|implode|psi|atmospher|temperature|cold|freez|boil|vent|smoker"),
 ("exploration-tech", r"submersible|submarine|rov\b|sonar|expedition|explore|dive|diver|titan|trieste|map"),
 ("earth-systems",    r"volcano|plate|tectonic|earthquake|tsunami|current|climate|geolog|mineral|mining"),
 ("space",            r"galaxy|galaxies|planet|universe|star|space|mars|moon|nasa|astronom"),
 ("method-evidence",  r"how do (?:we|they|scientists) know|how is .* measured|discover|evidence|proof|study|research"),
]

def bucket(q):
    for name, pat in DOMAINS:
        if re.search(pat, q): return name
    return None

d = json.load(open("mined_queries.json"))
rows = d["queries"]
kept, dropped = [], defaultdict(list)
for r in rows:
    q = r["query"]
    if any(re.search(p, q) for p in NOISE):  dropped["noise"].append(q);  continue
    if any(re.search(p, q) for p in BARRED): dropped["barred"].append(q); continue
    if r["words"] < 3:                       dropped["too_short"].append(q); continue
    b = bucket(q)
    if not b:                                dropped["off_taxonomy"].append(q); continue
    r["domain"] = b
    kept.append(r)

# rank: multi-seed confirmation, then question form, then specificity
kept.sort(key=lambda r: (-r["seed_hits"], -r["is_question"], -r["words"]))
out = {"source": "mined_queries.json", "mined_at": d["mined_at"],
       "kept": len(kept), "dropped": {k: len(v) for k, v in dropped.items()},
       "queries": kept}
json.dump(out, open("topic_backlog.json", "w"), indent=2)

print(f"in {len(rows)}  ->  kept {len(kept)}")
for k, v in dropped.items(): print(f"   dropped {k:<14} {len(v)}")
print()
by = defaultdict(int)
for r in kept: by[r["domain"]] += 1
for k, v in sorted(by.items(), key=lambda x: -x[1]): print(f"   {k:<20} {v}")
print("\nTop questions, multi-seed confirmed:")
for r in [x for x in kept if x["is_question"] and x["seed_hits"] >= 2][:18]:
    print(f"   {r['seed_hits']:>2}x [{r['domain'][:16]:<16}] {r['query']}")
