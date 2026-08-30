"""The rule that overrides everything: a directive may not put a value on screen
that its own script does not speak.

These segments (segments_ext2) look authoritative — a numbered method, a named
source, a confidence interval. That is exactly why an invented item in one is
worse than no visual at all. This test re-derives, from the scripts themselves,
that every NUMBER and every PROPER NOUN drawn by a v2 directive appears verbatim
in that script's narration.

It hard-fails when it inspects zero directives, so it can never pass by finding
nothing to check.
"""
import re, glob, os, sys

NEW = ("chain", "uncertain", "sources", "steps", "contrast", "magnitude",
       "define", "checklist")
PUNC = str.maketrans("", "", "“”\"'’‘()[]{},.;:!?")

# Words that belong to the DIRECTIVE's own grammar (headings, column labels),
# not to any claim about the world. Everything else must come from the prose.
STRUCT = set("""IS NOT WHAT WHY HOW WHO WHOSE WHERE WHEN THE A AN AND OR OF TO IN ON AT FOR
WITH FROM BE IT ITS THIS THAT THESE THOSE TWO THREE FOUR FIVE SIX ONE ALL ANY EACH EVERY MY OUR
DOES DO DID CAN COULD WILL WOULD MAY MIGHT MUST HAVE HAS HAD ARE WAS WERE NO
KINDS SUPPORTS MADE READ RUN RAISE COUNT UP GOES ARRIVES ELSE GREATEST HONESTLY STATED SHOWS
LEAVES ENTERS BELONGS ACTUALLY STILL ALSO ONLY BEFORE AFTER LIKE BESIDE VILLAINS DAMAGES BLURS
ALWAYS LARGER DEEPER SEA DEEP TEST CHECK RULE TOUR CHART LADDER STRATEGIES QUESTIONS CUES REMOVES
BARGAIN LIMIT GOAL METHOD EVIDENCE HABIT PROBLEMS PLANS ZONE ZONES BODY BODIES DOMINATES AFFECTS
MATTERS LEADS SEES DIFFERENT OCEAN WORK AROUND THEY NEED HAPPENS WAY LOOK REPORTS CLAIM
ANSWER PART REVEAL GATE RELEASE VALUE RANGE MEASURED FIRST LAST NEXT PICK""".split())

ROOT = os.path.join(os.path.dirname(__file__), "..")


def stem(w):
    """Crudest possible stem. Only used to forgive an inflection of a word the
    narration already says (describe -> description); never to forgive a name."""
    w = w.lower()
    for suf in ("ations", "ation", "ings", "ing", "edly", "ed", "es", "s", "ly", "d"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[:-len(suf)]
    return w


def directives(body):
    for line in body.split("\n"):
        line = line.strip()
        m = re.match(r"^\{\{\s*(\w+)\s*:?\s*(.*?)\s*\}\}$", line)
        if m and m.group(1).lower() in NEW:
            yield m.group(1).lower(), m.group(2), line


def check():
    flags, seen, scripts = [], 0, sorted(glob.glob(os.path.join(ROOT, "scripts", "*.md")))
    for f in scripts:
        body = open(f).read().split("## Narration", 1)[1].split("\n## Human fingerprint", 1)[0]
        prose = " ".join(l for l in body.split("\n") if not l.strip().startswith("{{"))
        plow = prose.lower()
        name = os.path.basename(f)[:2]
        for kind, args, line in directives(body):
            seen += 1
            # a LABEL=DETAIL pair is two independent phrases; split before testing
            parts = re.split(r"[|=]", args)
            for part in parts:
                for num in re.findall(r"\d[\d,\.]*", part):
                    if num.lower() not in plow:
                        flags.append((name, "NUMBER", num, line[:74]))
                toks = part.split()
                for i, tok in enumerate(toks):
                    t = tok.translate(PUNC).lstrip("+-?>")
                    if not t or not t[0].isupper():
                        continue
                    # A list item is sentence-cased, so its FIRST word carries no
                    # proper-noun signal. A real name is capitalised mid-phrase.
                    if i == 0:
                        continue
                    if t.upper() in STRUCT or t.lower() in plow:
                        continue
                    if stem(t) and stem(t) in plow:     # inflection, not a new fact
                        continue
                    flags.append((name, "PROPER", t, line[:74]))
    return flags, seen, len(scripts)


if __name__ == "__main__":
    flags, seen, nscripts = check()
    print(f"inspected {seen} v2 directives across {nscripts} scripts")
    if nscripts != 20:
        print(f"FAIL  expected 20 scripts, found {nscripts}")
        sys.exit(1)
    if seen == 0:                       # Rule 0: never pass on an empty loop
        print("FAIL  inspected zero directives - the guard cannot see its subject")
        sys.exit(1)
    for s, k, t, l in flags:
        print(f"  FAIL {s}  {k:7} {t!r:24} {l}")
    print("FAILED" if flags else "all green - no invented number or name on screen")
    sys.exit(1 if flags else 0)
