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
STRUCT = set("""IS NOT AND OR OF TO IN ON AT FOR WITH FROM A AN THE""".split())

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
            # Field 0 is the directive's TITLE (or the term of a define/contrast):
            # an editorial label chosen by the annotator, like a chapter heading.
            # It asserts nothing, so only its NUMBERS are checked. Every LATER
            # field is a CLAIM drawn on screen and is checked in full.
            fields = args.split("|")
            for num in re.findall(r"\d[\d,\.]*", fields[0]):
                if num.lower() not in plow:
                    flags.append((name, "NUMBER", num, line[:74]))
            # a LABEL=DETAIL pair is two independent phrases; split before testing
            parts = re.split(r"[|=]", "|".join(fields[1:]))
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
                    # possessive: the apostrophe was stripped, so ROV's -> ROVs
                    if t.endswith("s") and t[:-1].lower() + "'s" in plow:
                        continue
                    flags.append((name, "PROPER", t, line[:74]))
    return flags, seen, len(scripts)


def check_parses():
    """A directive the planner cannot parse is silently ignored and the beat
    falls back to prose heuristics — it LOOKS annotated and renders nothing new.
    That is the 'runs but inert' failure, so it is a hard error, not a warning."""
    sys.path.insert(0, os.path.join(ROOT, "visuals"))
    import planner, segments_ext2                     # noqa: F401  (installs parser)
    dead, total = [], 0
    for f in sorted(glob.glob(os.path.join(ROOT, "scripts", "*.md"))):
        body = open(f).read().split("## Narration", 1)[1].split("\n## Human fingerprint", 1)[0]
        for kind, args, line in directives(body):
            total += 1
            got = planner.parse_directive(line)
            if got is None:
                dead.append((os.path.basename(f)[:2], line[:74]))
                continue
            seg, kw = got
            getattr(segments_ext2, seg)(0.7, **kw)     # must also RENDER
    return dead, total


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
    dead, total = check_parses()
    print(f"{total} v2 directives parse and render, {len(dead)} inert")
    for n, l in dead:
        print(f"  FAIL {n}  directive does not parse - beat falls back silently: {l}")
    ok = not flags and not dead
    print("all green - no invented number or name on screen" if ok else "FAILED")
    sys.exit(0 if ok else 1)
