"""Materials-and-manufacturing's structural-device renderers.

The materials equivalent of `visuals/segments.py`'s `depth_descent` and
`zone_column` — NOT those functions made generic. Ocean depth's device is
"light dies with depth": colour is subtracted as the axis increases. A metal
heating is the physical inverse: colour is EMITTED as the axis increases
(blackbody incandescence — a real, cited phenomenon, not a decorative
choice). Sharing one parameterised function across an additive and a
subtractive colour model would have produced exactly the "ocean device
recoloured" outcome this domain was told to avoid, so this is a separate
module with its own two functions instead, built from `visuals/domains.py`'s
materials DEVICE (title/unit/max/bands) rather than from deep sea's ZONES.

`visuals/assemble.py` discovers these the same way it discovers
`segments_ext`/`segments_ext2`: an optional import, looked up by function
name in `seg_fn()`. A materials plan references `thermal_ascent` or
`process_column` by name in its beat's `"segment"` field; a deep-sea plan
never does, because deep-sea scripts never emit a `{{thermal}}` or
`{{stages}}` directive (see visuals/planner.py, visuals/CONTRACT.md).
"""
from design import (AMBER, CYAN, DEVICE, F_DISPLAY, F_LABEL, F_MONO,
                    INK, MID, MUTED, PALE, TEXT, W, H, ease, mix)
from segments import _center, _grad, _snow, font  # shared drawing helpers —
                                                   # domain-agnostic already


# Blackbody-inspired stops along the materials thermal axis: cold graphite,
# through the palette's own MID (ember) / CYAN (forge orange) / PALE (temper
# straw) accents, to AMBER (arc/plasma white-blue) at the top. Uses the
# ACTIVE domain's own palette constants (imported above), so this stays
# correct even if visuals/domains.py's materials palette is retuned later —
# nothing here hardcodes an RGB triple a second time.
_STOPS = [
    (0,    INK),
    (600,  MID),
    (1300, CYAN),
    (2500, PALE),
    (6000, AMBER),
]


def temperature_color(c):
    """Colour at a given temperature in Celsius. Heat is born, not lost."""
    for i in range(len(_STOPS) - 1):
        v0, c0 = _STOPS[i]
        v1, c1 = _STOPS[i + 1]
        if c < v1:
            t = 0.0 if v1 == v0 else max(0.0, (c - v0) / (v1 - v0))
            return mix(c0, c1, min(1.0, t))
    return _STOPS[-1][1]


def thermal_ascent(t, to_temp=None, label=None):
    """Signature shot: a continuous rise through the thermal scale.

    Materials' analogue of depth_descent — an ascent rather than a descent,
    because the axis this domain organises around runs from cold to hot, not
    surface to abyss.
    """
    to_temp = to_temp if to_temp is not None else DEVICE["max"]
    label = label if label is not None else DEVICE.get(
        "default_ascent_label", DEVICE.get("title", ""))
    e = ease(t); cur = to_temp * e
    img = _grad(temperature_color(cur * 0.25), temperature_color(cur))
    from PIL import Image, ImageDraw
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    _snow(d, t, n=90, speed=0.5)
    step = 500
    first = int(cur // step) * step
    for i in range(-2, 9):
        c = first - i * step
        if c < 0 or c > to_temp: continue
        y = H * 0.5 + (cur - c) * (H / 3400)
        if -60 < y < H + 60:
            major = c % 1000 == 0
            d.line([(W - 300, y), (W - (250 if major else 275), y)],
                   fill=(*CYAN, 200 if major else 90), width=2 if major else 1)
            if major:
                d.text((W - 245, y - 13), f"{c:,}°C", font=font(F_MONO, 22),
                       fill=(*CYAN, 210))
    d.line([(W - 300, 0), (W - 300, H)], fill=(*CYAN, 45), width=1)
    _center(d, f"{int(cur):,}", font(F_DISPLAY, 150), H * 0.40, (*TEXT, 255))
    _center(d, "DEGREES C", font(F_LABEL, 30), H * 0.40 + 205, (*MUTED, 210),
           spacing=10)
    _center(d, label.upper(), font(F_LABEL, 26), 70, (*CYAN, 190), spacing=7)
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def process_column(t, highlight=None):
    """The thermal scale, five bands. Materials' analogue of zone_column —
    compressed axis (sqrt) so the low-temperature bands stay legible, the
    axis labelled with real values so the compression is visible, not
    hidden, exactly as the ocean version discloses its own compression."""
    from PIL import Image, ImageDraw
    bands = DEVICE["bands"]
    axis_max = DEVICE["max"]
    img = _grad(MID, INK)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    _snow(d, t, n=70, speed=0.3)
    x0, x1 = W * 0.26, W * 0.52
    top_y, bot_y = 165, H - 165
    hl = (highlight or "").strip().upper() or None

    def ypos(c):
        return top_y + (c / axis_max) ** 0.5 * (bot_y - top_y)

    prev_label_y = -999
    for i, (name, lo, hi) in enumerate(bands):
        yt, yb = ypos(lo), ypos(hi)
        rev = ease(max(0, min(1, t * 4.5 - i * 0.5)))
        if rev <= 0: continue
        h = (yb - yt) * rev
        on = (hl is None) or (hl == name)
        c = temperature_color((lo + hi) / 2)
        fill = mix(c, PALE, 0.16 if on else 0.05)
        d.rectangle([x0, yt, x1, yt + h], fill=(*fill, 255))
        d.line([(x0, yt), (x1, yt)], fill=(*CYAN, 200 if on else 70), width=2)
        if rev > 0.9:
            ly = max(yt + 8, prev_label_y + 62)
            a = 255 if on else 120
            col = CYAN if on else MUTED
            d.line([(x1 + 8, ly + 14), (x1 + 26, ly + 14)], fill=(*col, a), width=2)
            d.text((x1 + 36, ly), name, font=font(F_LABEL, 26), fill=(*col, a))
            d.text((x1 + 36, ly + 30), f"{lo:,}-{hi:,}°C",
                   font=font(F_MONO, 19), fill=(*MUTED, a))
            prev_label_y = ly
    d.line([(x0, top_y), (x0, bot_y)], fill=(*CYAN, 90), width=1)
    _center(d, DEVICE["title"], font(F_LABEL, 26), 72, (*CYAN, 200), spacing=8)
    d.text((x0 - 150, bot_y - 10), f"{axis_max:,}°C", font=font(F_MONO, 19),
           fill=(*MUTED, 150))
    d.text((x0 - 150, top_y - 6), "0°C", font=font(F_MONO, 19), fill=(*MUTED, 150))
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


# ---------------------------------------------------------------------------
# Planner graft. The materials directive pack lives WITH the materials
# renderers, the way segments_ext2 keeps its own `install()` beside the
# functions it parses for. Two scripts already emit `{{thermal}}` and
# `{{stages}}`; before this existed neither directive was parsed by anything,
# so both fell through to the heuristics and were drawn as plain typography —
# the renderers above were unreachable from a script.
#
# Grafted only when the ACTIVE domain declares this device. A deep-sea script
# that happened to write `{{thermal: 900}}` must not silently get a materials
# card: the domain is what decides, not the presence of the word.
# ---------------------------------------------------------------------------

_installed = False


def parse_directive_materials(kind, raw):
    """`{{thermal: <celsius> | <label>}}` and `{{stages: <BAND>}}`."""
    parts = [p.strip() for p in raw.split("|")] if raw else []
    try:
        if kind == "thermal":
            if not parts or not parts[0]:
                return ("thermal_ascent", {})
            return ("thermal_ascent",
                    {"to_temp": int(float(parts[0].replace(",", "").rstrip("Cc° "))),
                     "label": parts[1] if len(parts) > 1 else None})
        if kind == "stages":
            return ("process_column",
                    {"highlight": parts[0].upper() if parts and parts[0] else None})
    except Exception:
        return None            # malformed -> ignore, fall back to heuristics
    return None


def install(planner=None):
    """Teach the planner `{{thermal}}` and `{{stages}}`. Idempotent."""
    global _installed
    if planner is None:
        try:
            import planner as planner                  # noqa: PLW0127
        except ImportError:
            return False
    if getattr(planner, "_materials_installed", False):
        _installed = True
        return True

    base = planner.parse_directive
    rx = planner.DIRECTIVE

    def parse_directive(line):
        got = base(line)
        if got is not None:
            return got
        m = rx.match(line.strip())
        if not m:
            return None
        return parse_directive_materials(m.group(1).lower(), m.group(2))

    parse_directive.__doc__ = base.__doc__
    planner.parse_directive = parse_directive
    planner._materials_installed = True

    # ---- the heuristic signal set, replaced rather than extended --------
    # planner.SIGNALS is deep sea's: it fires zone_column on "zone", and
    # depth_descent on "deeper" or "down to". A script about a welding arc
    # says "deeper into the weld pool" and got two depth_descent beats and
    # four light_attenuation beats - the ocean's "light dies with depth"
    # card - for a domain whose whole device is the physical inverse. So the
    # ocean-only entries are REPLACED, not appended to: keeping them and
    # merely ranking materials higher would still let them win a sentence
    # that happened not to mention heat.
    #
    # Kept, because they are domain-agnostic already: stat_card, comparison,
    # size_ladder, timeline. Dropped: light_attenuation, depth_descent,
    # pressure_gauge (its args are a depth in metres), zone_column (this
    # domain's counterpart is process_column), world_map (find_places is a
    # hardcoded list of ocean trenches), anatomy_callout (species anatomy).
    NUM = planner.NUM
    planner.SIGNALS = [
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
    planner.COLD_OPEN_SEGMENT = "thermal_ascent"

    # ---- args for the two device renderers, when chosen heuristically ---
    # planner.build_args is defined TWICE in that module (the second shadows
    # the first); wrapping whichever one is live avoids editing either copy.
    _base_args = planner.build_args

    def build_args(seg, beat):
        t = beat["text"]
        if seg == "thermal_ascent":
            import re as _re
            m = _re.search(r"([\d][\d,]*(?:\.\d+)?)\s*degrees?", t, _re.I)
            if not m:
                return None                 # no cited figure -> no thermal card
            return {"to_temp": int(float(m.group(1).replace(",", ""))),
                    "label": None}
        if seg == "process_column":
            return {"highlight": None}
        return _base_args(seg, beat)

    planner.build_args = build_args

    # thermal_ascent and process_column CARRY CONTENT — a temperature with a
    # cited figure, a named process stage. They are informational, exactly as
    # depth_descent and zone_column are for deep sea, so the filler pass must
    # never displace them (visuals/plan_species.py's rule, same reason).
    for attr in ("INFO", "INFORMATIONAL"):
        cur = getattr(planner, attr, None)
        if isinstance(cur, set):
            cur |= {"thermal_ascent", "process_column"}
    _installed = True
    return True
