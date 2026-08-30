"""Regression tests for the planner. Each check encodes a defect that actually
shipped into a render and cost a re-render to find. They must not come back."""
import sys, os, glob
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "visuals"))
import planner

FAIL = []
def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f"   {detail}"))
    if not cond: FAIL.append(name)

print("phrase extraction")
p = planner.key_phrase("Only vehicles designed for full-ocean depth can operate at "
                       "Challenger Deep; systems must survive pressure.")
check("completes a proper name", p.endswith("Challenger Deep"), repr(p))

p = planner.key_phrase("NOAA reports Challenger Deep at approximately 10,935 meters, "
                       "or 35,876 feet, below mean sea level.")
check("never splits inside a number", "10,935" in p, repr(p))

for t in ["The trench forms where one tectonic plate bends and descends beneath another.",
          "Microbes and invertebrates occupy trench sediments, while the deepest fishes live above.",
          "Challenger Deep is a depression at the southern end of the Mariana Trench."]:
    p = planner.key_phrase(t)
    last = p.split()[-1].lower().strip(",")
    check(f"no dangling end: {p[:32]!r}", last not in planner.DANGLING, f"ends {last!r}")

check("short input passes through",
      planner.key_phrase("That uncertainty matters") == "That uncertainty matters")
check("wrap_lines never empty",
      all(planner.wrap_lines(t) for t in ["a b c d e f g h i j k l", "Short one."]))

print("directives")
check("malformed ignored", planner.parse_directive("{{stat:}}") is None)
check("unknown ignored",   planner.parse_directive("{{bogus: x}}") is None)
check("stat parses",       planner.parse_directive("{{stat: 10,935 | METRES}}")[0] == "stat_card")
check("compare needs two", planner.parse_directive("{{compare: Everest=8849}}") is None)

print("plans over all scripts")
INFO = {"stat_card","depth_descent","comparison","zone_column","pressure_gauge",
        "light_attenuation","world_map","timeline","anatomy_callout","size_ladder"}
KNOWN = INFO | {"text_beat","quote_card","ambient_drift"}
scripts = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "scripts", "*.md")))
check("found 20 scripts", len(scripts) == 20, str(len(scripts)))
if not scripts: sys.exit(1)

worst, empty, unknown, dangle = 0, 0, set(), 0
for f in scripts:
    plan = planner.plan(f)
    run = cur = 1; prev = None
    for b in plan:
        if b["segment"] not in KNOWN: unknown.add(b["segment"])
        if b.get("args") is None: empty += 1
        for ln in (b["args"] or {}).get("lines", []) or []:
            pass
        if b["segment"] == prev: cur += 1; worst = max(worst, cur)
        else: cur = 1
        prev = b["segment"]
    # every text beat's last line must not dangle
    for b in plan:
        lines = (b.get("args") or {}).get("lines")
        if lines and lines[-1].split()[-1].lower().strip(",") in planner.DANGLING:
            dangle += 1

check("no run exceeds 2", worst <= 2, f"worst run {worst}")
check("no null args", empty == 0, str(empty))
check("no unknown segment types", not unknown, str(unknown))
check("no text beat ends on a dangling word", dangle == 0, f"{dangle} beats")

print()
print(f"FAILED: {len(FAIL)}" if FAIL else "all green")
sys.exit(1 if FAIL else 0)
