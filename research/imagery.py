"""Rights-checked imagery harvester for NOAA Ocean Exploration.

Route A of the thumbnail rebuild. The premise of this channel is evidence
discipline, so the rule here is the same one we apply to claims: nothing enters
the set unless the provenance is confirmed at the item page, not inferred from
the domain.

What NOAA actually says (https://oceanexplorer.noaa.gov/about/media-kit/,
checked 2026-08-30):

    "For images and videos posted on this website, we ask that you include the
    credit information included in the caption associated with each image or
    video. If space is limited, please credit NOAA Ocean Exploration
    (preferred) or NOAA. A limited number of images and videos posted on the
    website are copyrighted. If the image caption includes the word
    'copyright', additional permissions are required for use."

That is a per-item rule, so it must be enforced per item. Being on a .gov host
proves nothing: a survey of ~40 deep-sea items found roughly 40% credited to
third parties who are NOT federal — MBARI, Ocean Exploration Trust,
UW/NSF-OOI/WHOI, GFOE, and named individual photographers. Those are outside
17 U.S.C. 105 and are excluded.

So the gate is an allowlist, not a blocklist: the credit line must resolve to
NOAA and nobody else. Anything ambiguous is dropped. An empty set beats a
manifest full of guesses.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "channel", "imagery"))
ASSETS = os.path.join(OUT, "assets")
MANIFEST = os.path.join(OUT, "rights.json")

API = "https://oceanexplorer.noaa.gov/wp-json/wp/v2"
MEDIA_KIT = "https://oceanexplorer.noaa.gov/about/media-kit/"
UA = {"User-Agent": "Mozilla/5.0 (How We Know; thumbnail rights verification)"}

# ---------------------------------------------------------------- rights gate

# The credit must be NOAA and only NOAA. Leading "Image courtesy of" is common
# boilerplate and is stripped before matching. A trailing expedition name is
# fine — that is NOAA's own expedition, not a co-author.
CREDIT_OK = re.compile(
    r"^(?:image|photo|video)?\s*(?:courtesy\s+of\s+)?"
    r"noaa(?:\s+ocean\s+exploration|\s+office\s+of\s+ocean\s+exploration[\w\s]*)?"
    r"\s*[,.:;]?\s*(?P<rest>.*)$",
    re.I,
)

# If any of these survive in the credit after the NOAA prefix, a non-federal
# party has a stake in the work. Drop it. This list is deliberately broad; a
# false negative costs us one image, a false positive costs us a rights claim
# we cannot defend.
THIRD_PARTY = re.compile(
    r"(?i)\b("
    r"copyright|\(c\)|&copy;|"
    r"mbari|monterey bay|"
    r"ocean exploration trust|nautilus|"
    r"whoi|woods hole|"
    r"uw/|university|univ\.|college|institute|institution|"
    r"gfoe|global foundation|"
    r"schmidt|oceanx|nekton|"
    r"usgs|boem|onr|nsf|ooi|nasa|"
    r"photographer|courtesy of [a-z]+ [a-z]+|"
    r"llc|inc\.|ltd|foundation|aquarium|museum"
    r")\b"
)

# An expedition name is allowed to follow the NOAA credit, but only if it looks
# like a NOAA expedition label rather than a second organisation. We accept a
# short trailing phrase of words/digits and reject anything with a slash (the
# marker of a joint credit like "UW/NSF-OOI/WHOI").
EXPEDITION_OK = re.compile(r"^[\w\s‘’'&+.:\-]*$")


def _get(url: str, binary: bool = False, tries: int = 3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=45) as f:
                return f.read() if binary else f.read().decode("utf-8", "replace")
        except Exception as exc:  # network flake, not a rights problem
            last = exc
            time.sleep(1.5 * (i + 1))
    raise last


def _text(fragment: str) -> str:
    t = re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>", " ", fragment)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def scrape_credit(item_url: str) -> str | None:
    """Pull the Credit block off the item page. None if there isn't one.

    No credit means no confirmed provenance, which means we do not use it.
    """
    page = _get(item_url)
    m = re.search(r"(?is)>\s*Credit\s*<[^>]*>(.{0,600}?)(?:<h\d|<footer|</section)", page)
    if not m:
        m = re.search(r"(?is)Credit\s*</[^>]+>(.{0,400}?)</div", page)
    if not m:
        return None
    credit = _text(m.group(1))
    return credit or None


def credit_is_noaa_only(credit: str | None) -> tuple[bool, str]:
    """The whole rights decision, in one auditable place."""
    if not credit:
        return False, "no credit line on item page"
    if THIRD_PARTY.search(credit):
        return False, f"third-party or copyrighted credit: {credit!r}"
    m = CREDIT_OK.match(credit)
    if not m:
        return False, f"credit does not resolve to NOAA alone: {credit!r}"
    rest = m.group("rest").strip().rstrip(".")
    if rest and (not EXPEDITION_OK.match(rest) or "/" in rest):
        return False, f"credit carries a co-author: {credit!r}"
    return True, "NOAA-only credit, no copyright notice"


# ---------------------------------------------------------------- harvesting

def search(term: str, per_page: int = 8) -> list[dict]:
    q = urllib.parse.quote(term)
    url = (f"{API}/multimedia?search={q}&per_page={per_page}"
           f"&_fields=id,link,title,content,featured_media")
    try:
        return json.loads(_get(url))
    except Exception:
        return []


def media_detail(mid: int) -> dict | None:
    try:
        return json.loads(_get(f"{API}/media/{mid}?_fields=id,source_url,media_details,mime_type"))
    except Exception:
        return None


def harvest(terms: dict[str, list[str]], per_term: int = 8, want: int = 3) -> list[dict]:
    """terms maps a slot name -> search phrases. Returns accepted records."""
    os.makedirs(ASSETS, exist_ok=True)
    accepted: list[dict] = []
    rejected: list[dict] = []
    seen_media: set[int] = set()

    for slot, phrases in terms.items():
        got = 0
        for phrase in phrases:
            if got >= want:
                break
            for item in search(phrase, per_term):
                if got >= want:
                    break
                mid = item.get("featured_media")
                if not mid or mid in seen_media:
                    continue
                seen_media.add(mid)

                credit = scrape_credit(item["link"])
                ok, why = credit_is_noaa_only(credit)
                if not ok:
                    rejected.append({"slot": slot, "item_url": item["link"],
                                     "title": _text(item["title"]["rendered"]),
                                     "credit": credit, "reason": why})
                    continue

                det = media_detail(mid)
                if not det or not det.get("mime_type", "").startswith("image/"):
                    continue
                md = det.get("media_details", {})
                if md.get("width", 0) < 1200:
                    rejected.append({"slot": slot, "item_url": item["link"],
                                     "reason": f"too small: {md.get('width')}px"})
                    continue

                src = det["source_url"]
                fname = f"{slot}__{mid}__{os.path.basename(urllib.parse.urlparse(src).path)}"
                path = os.path.join(ASSETS, fname)
                try:
                    blob = _get(src, binary=True)
                except Exception as exc:
                    rejected.append({"slot": slot, "item_url": item["link"],
                                     "reason": f"download failed: {exc}"})
                    continue
                with open(path, "wb") as f:
                    f.write(blob)

                accepted.append({
                    "slot": slot,
                    "search_phrase": phrase,
                    "title": _text(item["title"]["rendered"]),
                    "caption": _text(item.get("content", {}).get("rendered", "")),
                    "source_org": "NOAA Ocean Exploration",
                    "item_url": item["link"],
                    "direct_url": src,
                    "local_file": os.path.relpath(path, OUT),
                    "width": md.get("width"),
                    "height": md.get("height"),
                    "rights_basis": (
                        "Work of the U.S. federal government published by NOAA Ocean "
                        "Exploration. Item page credit resolves to NOAA alone with no "
                        "third-party co-credit and no copyright notice, which is the "
                        "test NOAA's own media kit sets for reuse."
                    ),
                    "rights_check": why,
                    "media_kit_url": MEDIA_KIT,
                    "required_credit": credit,
                    "commercial_use_permitted": True,
                    "date_checked": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "sha256": hashlib.sha256(blob).hexdigest(),
                    "bytes": len(blob),
                })
                got += 1
                time.sleep(0.2)

    manifest = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "policy": (
            "Accept only items whose NOAA item-page credit resolves to NOAA alone. "
            "Reject any credit naming a non-federal partner (MBARI, Ocean Exploration "
            "Trust, WHOI/UW, GFOE, universities, named individual photographers) or "
            "containing a copyright notice. Reject items with no credit line. "
            "Presence on a noaa.gov host is not evidence of public domain."
        ),
        "media_kit_url": MEDIA_KIT,
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "assets": accepted,
        "rejected": rejected,
    }
    os.makedirs(OUT, exist_ok=True)
    with open(MANIFEST, "w") as f:
        json.dump(manifest, f, indent=2)
    return accepted


TERMS = {
    "anglerfish":    ["anglerfish", "chaunacops", "coffinfish"],
    "jelly":         ["deep sea jellyfish", "narcomedusae", "benthocodon"],
    "siphonophore":  ["siphonophore"],
    "octopus":       ["dumbo octopus", "grimpoteuthis", "deep sea octopus"],
    "squid":         ["deep sea squid", "bathyteuthis", "magnapinna"],
    "vent":          ["hydrothermal vent chimney", "black smoker"],
    "crab":          ["squat lobster", "deep sea crab", "galatheid"],
    "sponge":        ["glass sponge", "hexactinellid", "venus flower basket"],
    "coral":         ["bubblegum coral", "iridogorgia", "bamboo coral"],
    "cucumber":      ["sea cucumber", "holothurian", "sea pig"],
    "star":          ["brisingid sea star", "basket star", "crinoid"],
    "fish":          ["rattail fish", "grenadier", "cusk eel", "tripodfish"],
    "whalefall":     ["whale fall", "whale bone"],
    "seafloor":      ["abyssal seafloor sediment", "manganese nodules"],
    "vehicle":       ["remotely operated vehicle deep discoverer", "rov dive"],
    # episode-specific probes
    "yeti_crab":     ["yeti crab", "kiwa"],
    "frilled_shark": ["frilled shark", "deep sea shark", "sixgill shark"],
    "snailfish":     ["snailfish", "liparid", "hadal trench"],
    "whale_bone":    ["whale fall bone", "whale skeleton seafloor"],
    "trench":        ["mariana trench", "challenger deep", "trench dive"],
    "biolum":        ["bioluminescent", "bioluminescence deep sea"],
    "eyes":          ["big eye fish deep sea", "deep sea fish eye"],
    "transparent":   ["transparent sea cucumber", "translucent deep sea"],
    "red_animal":    ["red deep sea shrimp", "red jellyfish deep"],
    "column":        ["midwater water column", "midnight zone"],
}

if __name__ == "__main__":
    got = harvest(TERMS)
    with open(MANIFEST) as f:
        man = json.load(f)
    print(f"accepted {man['accepted_count']} / rejected {man['rejected_count']}")
    print(f"manifest -> {MANIFEST}")
    from collections import Counter
    print("by slot:", dict(Counter(a["slot"] for a in got)))
    reasons = Counter(re.sub(r":.*", "", r.get("reason", "?")) for r in man["rejected"])
    for r, n in reasons.most_common():
        print(f"  rejected {n:3}  {r}")
