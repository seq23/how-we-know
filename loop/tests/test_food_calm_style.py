"""The food lane renders in the calm style; no other lane does.

THE RULING (owner, 2 Nov 2026): "The food videos need to focus on
hypnotizing imagery and pretty mesmerizing images that get people to be hooked
disassociate and fall asleep to the point is almost asmr" - "Don't give me a
sample just do it going forward" - "We can have videos with long amount of
imagery with no talking too or limited talking" - "we can aim for 15 min
videos". config/food_style.json is that style; visuals/food_style.py is its
one reader.

WHAT THIS PROVES
  1. The food lane's render code takes the calm values from the style: picture
     holds, crossfade and body treatment (visuals/food.py), voice settings
     (voice/food_voice.registers), the bed level (visuals/food_sound), the
     runtime window (visuals/food_episode) and the author's aim and kit
     searches (loop/food_author).
  2. Imagery-only holds land in a food segment's voice plan, never in the cold
     open or the tail.
  3. The reused-content guard: a run voiced under narration.share_min, or with
     an unvoiced stretch over silence_max_s, fails food_voice.check.
  4. Other lanes do not get it: for_lane() is None for deep sea and materials,
     and no module outside the food lane imports food_style.
Prove-it-fails: set "lanes": [] in config/food_style.json -> case 1 fails;
make food_style.style_of_text ignore the stamp -> case 1 fails;
add "deep-sea" to it -> case 4 fails; restore -> green.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

os.environ.setdefault("LOOP_DRY_RUN", "1")
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(ROOT / "visuals"))
sys.path.insert(0, str(ROOT / "voice"))

import food_style as FS                                        # noqa: E402

fails: list[str] = []
examined = 0


def check(ok: bool, msg: str) -> None:
    global examined
    examined += 1
    if not ok:
        fails.append(msg)


S = FS.STYLE
style = FS.for_lane("food-science")
check(style is not None, "the food-science lane does not get the food style")

# 1. the food lane's render code takes the calm values --------------------------
if style:
    import food                                                # noqa: E402
    import food_episode as FE                                  # noqa: E402
    import food_sound                                          # noqa: E402
    import food_voice                                          # noqa: E402
    import food_author as A                                    # noqa: E402
    pic = S["picture"]
    # an episode is calm by its script's stamp; the author stamps every new one
    stamped = (A.FOOD_DIR / "what-is-inside-butter-rice-meat.md")
    check(FS.style_of_text(stamped.read_text()) is style if stamped.exists() else True,
          "the in-flight butter/rice/meat script is not stamped calm")
    check(FS.style_of_text(FS.stamp()) is style, "the author's stamp does not read back as calm")
    check(FS.style_of_text("**Domain:** food-science") is None, "an unstamped script reads as calm")
    calm = food.styled_preset(style)
    check(calm["body_hold_s"] == tuple(pic["body_hold_s"]),
          f"calm body holds {calm['body_hold_s']}, not the style's {pic['body_hold_s']}")
    check(calm["crossfade_s"] == pic["crossfade_s"], "calm crossfade is not the style's")
    check(S["id"] in calm["id"], f"preset id {calm['id']} does not name the style")
    check(food.styled_preset(None) == food.BASE_PRESET, "the old preset changed")
    with food.styled(style):
        check(food.treatment_for({"uses": ["subject"]}, "body") == pic["body_treatment"],
              "a plain body clip is not slowed down")
    check(food.treatment_for({"uses": ["subject"]}, "body") == "play",
          "the old style lost its real-speed body clips")
    check(FS.style_of_spec({"preset": calm}) is style and
          FS.style_of_spec({"preset": food.BASE_PRESET}) is None,
          "a spec is not judged by the preset it was made in")
    reg = food_voice.registers(style)["registers"]["standard"]
    for k, v in S["voice"].items():
        check(reg.get(k) == v, f"voice {k} = {reg.get(k)}, not the style's {v}")
    base = food_voice.registers()["registers"]["standard"]
    check(base.get("pause_paragraph_s") != S["voice"]["pause_paragraph_s"],
          "an unstyled plan got the calm voice")
    check(food.bed_db_for(style) == S["sound"]["bed_db"], "calm bed is not the style's")
    check(food.bed_db_for(None) == food_sound.BASE_BED_DB, "the old bed level changed")
    check(FE.minutes_for(style) == tuple(S["length"]["minutes"]),
          f"calm window {FE.minutes_for(style)}, not the style's {S['length']['minutes']}")
    check(FE.minutes_for(None) == FE.EPISODE_MINUTES, "the old window changed")
    check(A.AIM_MINUTES == S["length"]["aim_minutes"], f"author aims {A.AIM_MINUTES} min")
    qs = {q["query"] for q in A.build_kit("butter")["queries"]}
    check(all(a.format(f="butter") in qs for a, _, _ in pic["extra_queries"]),
          "the kit lacks the style's mesmerising searches")

    # 2. imagery-only holds ------------------------------------------------------
    plan = [{"section": "Butter: Q"}, {"section": "Butter: Q"}, {"section": "Butter: Why"}]
    holds = [FE.imagery_only_s(plan, k, "butter", style) for k in range(3)]
    check(holds == [0.0, S["imagery_only"]["after_section_s"], S["imagery_only"]["after_segment_s"]],
          f"holds {holds}: not after the section and the segment")
    check(FE.imagery_only_s(plan, 2, "open", style) == 0 and
          FE.imagery_only_s(plan, 2, "tail", style) == 0,
          "an imagery-only hold in the cold open or tail")
    check(FE.imagery_only_s(plan, 2, "butter", None) == 0, "an unstamped episode got a hold")

    # 3. reused-content guard ----------------------------------------------------
    def meas(spoken: list[float], total: list[float]) -> dict:
        return {"beats": [{"index": i, "spoken_s": s, "total_s": t, "words": 60, "style": S["id"]}
                          for i, (s, t) in enumerate(zip(spoken, total))]}
    n = S["narration"]
    ok = meas([30, 30, 30], [34, 34, 40])
    check(not food_voice.narration_problems(ok), f"a well-voiced run fails: "
                                                 f"{food_voice.narration_problems(ok)}")
    thin = meas([10, 10, 10], [30, 30, 30])
    check(any("narration covers" in x for x in food_voice.narration_problems(thin)),
          "a run voiced a third of the time passes the reused-content guard")
    gap = meas([30, 30, 5], [34, 34, 5 + n["silence_max_s"] + 5])
    check(any(x.startswith("unvoiced") for x in food_voice.narration_problems(gap)),
          "an unvoiced stretch over silence_max_s passes")
    old = {"beats": [{k: v for k, v in b.items() if k != "style"} for b in thin["beats"]]}
    check(not food_voice.narration_problems(old), "an old-style voice was held to the calm rule")
    check(not any(x.startswith("beat ") for x in food_voice.narration_problems(gap)),
          "a hold problem is worded 'beat N' - the food night would re-draw it in vain")

# 4. no other lane ---------------------------------------------------------------
for lane in ("deep-sea", "materials", None):
    check(FS.for_lane(lane) is None, f"lane {lane!r} gets the food style")
FOOD_LANE = {"visuals/food.py", "visuals/food_episode.py", "visuals/food_sound.py",
             "visuals/food_style.py", "voice/food_voice.py", "loop/food_author.py",
             "loop/tests/test_food_calm_style.py"}
seen = 0
for p in list(ROOT.glob("loop/**/*.py")) + list(ROOT.glob("visuals/**/*.py")) + \
        list(ROOT.glob("voice/**/*.py")) + list(ROOT.glob("bin/*")):
    if not p.is_file():
        continue
    seen += 1
    rel = str(p.relative_to(ROOT))
    if rel in FOOD_LANE:
        continue
    try:
        txt = p.read_text(errors="ignore")
    except OSError:
        continue
    check(not re.search(r"^\s*(import food_style|from food_style)", txt, re.M),
          f"{rel} imports the food style - only the food lane may")
check(seen > 50, f"scanned only {seen} source files")

if examined == 0:
    fails.append("examined nothing")
print(f"examined {examined} case(s)")
for f in fails:
    print("FAIL:", f)
sys.exit(1 if fails else 0)
