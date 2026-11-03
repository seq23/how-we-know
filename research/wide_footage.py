"""Wider public-domain footage harvest, by the episode's SHOT LIST subjects.

Owner, 2026-11-03: more variety ("a new image every 20 s"), and the harvest
widened before any fallback to moving photos. Two sources beyond what
research/imagery_video.py (oceanexplorer.noaa.gov) and
research/imagery_stock_video.py (Pixabay / Mixkit) already cover:

  * NOAA Ocean Exploration's video archive at NCEI (the OER video portal):
    dive HIGHLIGHT videos, searched by subject through NOAA OneStop. Works of
    the U.S. federal government. Files at NCEI are 640x360 ("Low"); they are
    taken anyway - real footage of the animal beats a moving photo.
  * Wikimedia Commons video whose own file page says Public domain or CC0.
    CC-BY is refused (CLAUDE.md: CC-BY is not a public-domain dedication).

Every clip is OCR-screened the way imagery_video.py screens NOAA clips: frames
every 2 s read with Apple Vision; a burned-in third-party credit or "Produced
by" line refuses the whole clip; only text-free spans become clean windows.
The vision vet in visuals/longform_picture.vet() then checks each span shows
the subject. Records go into channel/imagery/video_rights.json beside the rest.

    .venv/bin/python research/wide_footage.py SLUG [SLUG ...] [--per-subject N]
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
IMAGERY = os.path.join(ROOT, "channel", "imagery")
CLIPS = os.path.join(IMAGERY, "clips")
MANIFEST = os.path.join(IMAGERY, "video_rights.json")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "visuals"))

HARVESTER = {
    "domain": "deep-sea-ocean-science",
    "domains": ["deep-sea-ocean-science"],
    "manifest": "channel/imagery/video_rights.json",
    "what": "NOAA OER highlight video (NCEI) and Commons PD/CC0 video, by shot-list subject",
    "requires": ["ffmpeg", "swiftc"],
    "host": "mac-batch",
    "scheduled": False,
}
ONESTOP = "https://data.noaa.gov/onestop/api/search/search/granule"
COMMONS = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "HowWeKnow-footage/1.0 (https://howweknowdeep.com; rights-checked "
                    "public-domain footage for a documentary channel)"}
MAX_SECONDS = 240.0
MIN_SECONDS = 6.0
MIN_WIDTH = 640
PD_LICENCES = re.compile(r"^(public domain|pd|cc0|cc0 1\.0|pdm)", re.I)


def _json(url: str, body: dict | None = None, tries: int = 4):
    for k in range(tries):
        try:
            req = urllib.request.Request(
                url, data=json.dumps(body).encode() if body is not None else None,
                headers={**UA, **({"Content-Type": "application/json"} if body else {})})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and k < tries - 1:
                time.sleep(10 * (k + 1))
                continue
            raise


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


# ----------------------------------------------------------------- the sources

def oer_highlights(subject: str, n: int = 6) -> list[dict]:
    """NOAA OER dive highlight videos whose title, file name or keywords name
    the subject."""
    body = {"queries": [{"type": "queryText", "value": f'Highlight AND "{subject}"'}],
            "filters": [{"type": "facet", "name": "projects", "values": ["NOAAOceanExploration"]}],
            "page": {"max": n * 3, "offset": 0}}
    out = []
    for g in (_json(ONESTOP, body) or {}).get("data", []):
        a = g.get("attributes") or {}
        mp4 = next((l["linkUrl"] for l in a.get("links") or []
                    if str(l.get("linkUrl", "")).lower().endswith(".mp4")), None)
        if not mp4 or "highlight" not in (a.get("title") or "").lower():
            continue
        name = os.path.basename(mp4)
        m = re.match(r"(EX\d+)_VID_(\d{8})_(DIVE\d+)_(.+?)_Low\.mp4$", name, re.I)
        label = (m.group(4).replace("_", " ").title() if m else name)
        out.append({"source": "noaa-ncei-oer", "url": mp4, "id": name,
                    "title": f"{label} ({m.group(1)} {m.group(3).title()} highlight)" if m else label,
                    "caption": f"{label}. {a.get('title') or ''}",
                    "expedition": m.group(1) if m else "",
                    "credit": f"NOAA Ocean Exploration, {m.group(1)}" if m else "NOAA Ocean Exploration",
                    "item_url": f"https://www.ncei.noaa.gov/access/ocean-exploration/video/?oerkey=fileIdentifier:{name}",
                    "licence": "Public domain (work of the U.S. federal government, 17 U.S.C. 105)",
                    "rights_basis": "NOAA Ocean Exploration dive video archived at NCEI; "
                                    "a work of the U.S. federal government."})
        if len(out) >= n:
            break
    return out


def commons_videos(subject: str, n: int = 6) -> list[dict]:
    """Commons video files naming the subject whose own page says PD or CC0."""
    r = _json(COMMONS + "?" + urllib.parse.urlencode({
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f'"{subject}" filetype:video', "gsrnamespace": 6, "gsrlimit": 25,
        "prop": "imageinfo", "iiprop": "url|size|mediatype|extmetadata",
        "iiextmetadatafilter": "LicenseShortName|Artist|Credit|ImageDescription"}))
    out = []
    for p in ((r or {}).get("query") or {}).get("pages", {}).values():
        ii = (p.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata") or {}
        lic = re.sub("<[^>]+>", "", (md.get("LicenseShortName") or {}).get("value", "")).strip()
        title = p["title"][5:]
        if not PD_LICENCES.match(lic):
            continue
        if not re.search(r"\b" + re.escape(subject).replace(r"\ ", r"[\s_-]+"), title, re.I):
            continue
        if (ii.get("width") or 0) < MIN_WIDTH:
            continue
        artist = re.sub("<[^>]+>", "", (md.get("Artist") or {}).get("value", "")).strip()
        out.append({"source": "commons", "url": ii.get("url"), "id": title,
                    "title": os.path.splitext(title)[0].replace("_", " "),
                    "caption": re.sub("<[^>]+>", "", (md.get("ImageDescription") or {})
                                      .get("value", ""))[:300],
                    "credit": f"{artist[:60] or 'Wikimedia Commons'} (public domain, via Wikimedia Commons)",
                    "item_url": ii.get("descriptionurl"),
                    "licence": lic,
                    "rights_basis": f"Wikimedia Commons file page: {lic}."})
        if len(out) >= n:
            break
    return out


# ----------------------------------------------------------------- screening

def _probe(path: str) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height:format=duration", "-of", "json", path],
                       capture_output=True, text=True)
    d = json.loads(r.stdout or "{}")
    s = (d.get("streams") or [{}])[0]
    return {"width": s.get("width") or 0, "height": s.get("height") or 0,
            "seconds": float((d.get("format") or {}).get("duration") or 0)}


def screen_file(path: str, seconds: float) -> tuple[bool, str, list[dict]]:
    """OCR the clip; (ok, why, clean windows)."""
    import imagery_video as IV                          # noqa: PLC0415
    probes = IV.scan(path, seconds)
    ok, why = IV.gate_b(probes)
    if not ok:
        return False, why, []
    wins = IV.clean_windows(probes, seconds)
    if not wins:
        return False, "no text-free span of the minimum length", []
    return True, why, wins


def harvest(slugs: list[str], per_subject: int = 4) -> dict:
    import shot_list as SL                              # noqa: PLC0415
    man = json.load(open(MANIFEST)) if os.path.exists(MANIFEST) else {"assets": []}
    have = {a.get("post_id") for a in man.get("assets", [])}
    refused = {r.get("post_id") for r in man.get("wide_refused", [])}
    new, refusals = [], []
    os.makedirs(CLIPS, exist_ok=True)
    for slug in slugs:
        for subject in SL.subjects(slug):
            for fetch in (oer_highlights, commons_videos):
                try:
                    cands = fetch(subject, per_subject)
                except Exception as e:                  # noqa: BLE001
                    print(f"  {fetch.__name__} {subject!r}: {str(e)[:80]}")
                    continue
                for c in cands:
                    pid = f"{c['source']}:{c['id']}"
                    if pid in have or pid in refused:
                        continue
                    fname = f"wide__{c['source']}__{_slug(c['id'])}.{c['url'].rsplit('.', 1)[-1][:4]}"
                    path = os.path.join(CLIPS, fname)
                    try:
                        req = urllib.request.Request(c["url"], headers=UA)
                        blob = urllib.request.urlopen(req, timeout=300).read()
                    except Exception as e:              # noqa: BLE001
                        print(f"  download failed {pid}: {str(e)[:80]}")
                        continue
                    open(path, "wb").write(blob)
                    info = _probe(path)
                    why = None
                    if not (MIN_SECONDS <= info["seconds"] <= MAX_SECONDS):
                        why = f"{info['seconds']:.0f} s long"
                    elif info["width"] < MIN_WIDTH:
                        why = f"{info['width']} px wide"
                    if why is None:
                        ok, gate, wins = screen_file(path, info["seconds"])
                        if not ok:
                            why = gate
                    if why:
                        os.remove(path)
                        refusals.append({"post_id": pid, "reason": why})
                        refused.add(pid)
                        print(f"  refused {pid[:70]}: {why[:80]}")
                        continue
                    rec = {"post_id": pid, "source": c["source"], "title": c["title"],
                           "caption": c["caption"], "subject": subject, "episodes": [slug],
                           "source_org": "NOAA Ocean Exploration" if c["source"] == "noaa-ncei-oer"
                           else "Wikimedia Commons",
                           "item_url": c["item_url"], "direct_url": c["url"],
                           "local_file": f"clips/{fname}", "width": info["width"],
                           "height": info["height"], "seconds": info["seconds"],
                           "clean_windows": wins, "treatment": "as-shot", "crop": None,
                           "licence": c["licence"], "rights_basis": c["rights_basis"],
                           "rights_check": gate, "required_credit": c["credit"],
                           "attribution_required": False, "commercial_use_permitted": True,
                           "date_checked": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                           "sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob)}
                    new.append(rec)
                    have.add(pid)
                    print(f"  CLIP {slug[:34]:<34} {subject!r:<22} {pid[:60]}")
    man = json.load(open(MANIFEST)) if os.path.exists(MANIFEST) else {"assets": []}
    man["assets"] = man.get("assets", []) + new
    man["accepted_count"] = len(man["assets"])
    man["wide_refused"] = man.get("wide_refused", []) + refusals
    man["wide_generated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tmp = MANIFEST + ".tmp"
    json.dump(man, open(tmp, "w"), indent=2)
    os.replace(tmp, os.path.realpath(MANIFEST)) if os.path.islink(MANIFEST) else os.replace(tmp, MANIFEST)
    print(f"wide footage: {len(new)} new clip(s), {len(refusals)} refused")
    return {"new": len(new), "refused": len(refusals)}


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--pending" in sys.argv:                 # every episode waiting for a render
        import imagery_stock_video as STOCK     # noqa: PLC0415
        args = [s for s in STOCK.targets() if STOCK.domain_of(s) == "deep-sea-ocean-science"]
        if not args:
            print("wide footage: no deep-sea episode is waiting for a render")
            raise SystemExit(0)
    per = int(sys.argv[sys.argv.index("--per-subject") + 1]) if "--per-subject" in sys.argv else 4
    if not args:
        print(__doc__)
        raise SystemExit(2)
    r = harvest([a for a in args if not a.isdigit() and a != str(per)], per)
    raise SystemExit(0 if r["new"] or r["refused"] else 3)
