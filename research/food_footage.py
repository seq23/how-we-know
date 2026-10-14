"""Real moving food footage for the `food` preset: a free fallback CHAIN of sources.

    python research/food_footage.py --sources        # each adapter: enabled, or why not
    python research/food_footage.py --snapshot       # search every enabled adapter, record candidates
    python research/food_footage.py --resolve        # the chocolate shot list -> one clip per need
    python research/food_footage.py --harvest        # resolve, download, write the manifest
    python research/food_footage.py --verify         # rights fields + sha256 on disk

    # the fallback proof (owner, 2026-10-13): no Pixabay, still >= 10 real clips
    HWK_FOOTAGE_KEY_DIR=/nonexistent PIXABAY_API_KEY= python research/food_footage.py --resolve --offline

WHY (owner verdict on sample round 1, 2026-10-13): "stills are not acceptable"
- food in motion is REAL video, never an AI still with a zoom. No open video
model runs on the Mac (M2, 8 GB) and nothing paid is ever used.

THE CHAIN, in order. Every adapter has the same contract -
search(query) -> candidates; download(candidate) -> (meta, bytes); a licence
record - its licence wording stored under channel/imagery/licences/, a polite
gap between requests, and a TERMS verdict. An adapter whose site's terms forbid
automated access is DISABLED with that reason, never silently used.

  1. pixabay   Pixabay Content License (no attribution). Key file
               ~/.config/how-we-know/pixabay.key (mode 600) or $PIXABAY_API_KEY.
               API rules obeyed: <= 100 req/60 s, every response cached 24 h.
  2. pexels    Pexels License. Key file pexels.key or $PEXELS_API_KEY; dormant
               (Pexels paused new API keys on 2026-10-13).
  3. mixkit    Mixkit Stock Video Free License (YouTube + commercial, no
               attribution). User Terms cl. 9 forbid "scripts or bots to MASS
               download": one category page per need, MAX_PER_RUN downloads,
               MIXKIT_GAP_S apart, the FREE licence re-read on every item page.
     coverr    DISABLED: Website Terms forbid "robots, or any other automated
               means"; its API needs a key.
  4. commons   Wikimedia Commons video, public domain / CC0 only
               (imagery.pd_licence_ok, the stills' gate).
     archive   Internet Archive, ONLY the Prelinger and FedFlix (US government)
               collections and only items whose licenseurl is a PD/CC0 URL;
               user-uploaded "opensource_movies" PD marks are not trusted.
     nasa      NASA Image and Video Library (US government work, PD).

The chain falls through PER NEED: each need in SHOTS takes the first candidate,
in chain order, that matches its words, is not refused, and is not already
used. HWK_FOOTAGE_DISABLE=a,b turns adapters off; HWK_FOOTAGE_KEY_DIR moves the
key directory (the proof above points it at nothing - her key file is never
touched). Candidates found are recorded in channel/imagery/food_footage_candidates.json
so the proof also runs offline (CI), and loop/tests/test_food_footage_chain.py
holds the chain to it.

Clips never enter git (.gitignore: channel/imagery/clips/); the manifest
(channel/imagery/food_clips.json) and every sha256 do.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time
import urllib.parse
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
IMAGERY = ROOT / "channel" / "imagery"
CLIPS = IMAGERY / "clips"
API_CACHE = CLIPS / ".api-cache"
MANIFEST = IMAGERY / "food_clips.json"
CANDIDATES = IMAGERY / "food_footage_candidates.json"
UA = "Mozilla/5.0 (How We Know; footage licence verification; howweknowdeep.com)"
CACHE_S = 24 * 3600
MAX_PER_RUN = 20
MIXKIT_GAP_S = 4.0
MIN_REAL_CLIPS = 10

RIGHTS_FIELDS = ["source", "item_url", "download_url", "licence", "licence_url",
                 "fetched_at", "sha256", "local_file", "credit_line", "depicts",
                 "subject_basis"]
# Never footage, whatever its tags say: generated or drawn, or a brand on screen
# (Pixabay's licence bars branded content in commercial use).
BANNED_WORDS = ("ai generated", "ai-generated", "3d", "cartoon", "animation", "render",
                "cgi", "nutella", "snickers", "ferrero", "kinder", "m&m", "hershey",
                "ghirardelli", "milka", "lindt", "cadbury", "toblerone")


def key_dir() -> Path:
    return Path(os.environ.get("HWK_FOOTAGE_KEY_DIR") or os.path.expanduser("~/.config/how-we-know"))


def key_for(name: str) -> str | None:
    """A source's API key: key file (mode 600) first, then env. Never printed."""
    p = key_dir() / f"{name}.key"
    if p.exists():
        mode = stat.S_IMODE(p.stat().st_mode)
        if mode & 0o077:
            raise PermissionError(f"{p} is readable by others ({oct(mode)}); chmod 600")
        v = p.read_text().strip()
        if v:
            return v
    return os.environ.get(f"{name.upper()}_API_KEY") or None


# ---------------------------------------------------------------- network
_LAST: dict[str, float] = {}


def _get(url: str, binary: bool = False, gap: float = 1.0, host: str = "",
         headers: dict | None = None):
    host = host or urllib.parse.urlparse(url).netloc
    wait = gap - (time.monotonic() - _LAST.get(host, 0.0))
    if wait > 0:
        time.sleep(wait)
    _LAST[host] = time.monotonic()
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=180) as f:
                data = f.read()
            return data if binary else data.decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 3:
                raise
            time.sleep(15 * (attempt + 1))              # told to slow down: back off, never hammer
    raise RuntimeError("unreachable")


def _cached(name: str, fetch) -> object:
    """A search response cached 24 h on disk (Pixabay requires it; politeness for all).
    The cache key is the query, never the API key."""
    API_CACHE.mkdir(parents=True, exist_ok=True)
    c = API_CACHE / (re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:120] + ".json")
    if c.exists() and time.time() - c.stat().st_mtime < CACHE_S:
        return json.loads(c.read_text())
    v = fetch()
    c.write_text(json.dumps(v))
    return v


def probe(path: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate:format=duration", "-of", "json",
                        str(path)], capture_output=True, text=True, check=True)
    j = json.loads(r.stdout)
    st = j["streams"][0]
    n, d = (int(x) for x in st["r_frame_rate"].split("/"))
    return {"width": st["width"], "height": st["height"], "fps": round(n / max(d, 1), 3),
            "duration_s": round(float(j["format"]["duration"]), 3)}


# --------------------------------------------------------------- adapters
class Adapter:
    name = ""
    licence = ""
    licence_url = ""
    licence_text: str | None = None         # under channel/imagery/
    terms_url = ""
    terms_text: str | None = None
    terms_block: str | None = None          # set => disabled by the site's own terms
    needs_key: str | None = None
    credit = ""
    gap_s = 1.0

    def enabled(self) -> tuple[bool, str]:
        off = {x.strip() for x in (os.environ.get("HWK_FOOTAGE_DISABLE") or "").split(",")}
        if self.name in off:
            return False, "turned off by HWK_FOOTAGE_DISABLE"
        if self.terms_block:
            return False, f"terms forbid it: {self.terms_block}"
        if self.needs_key and not key_for(self.needs_key):
            return False, (f"no key: add {key_dir()}/{self.needs_key}.key (mode 600) or "
                           f"${self.needs_key.upper()}_API_KEY - no code change")
        return True, "usable"

    def search(self, query: str) -> list[dict]:            # pragma: no cover - per adapter
        raise NotImplementedError

    def download(self, cand: dict) -> tuple[dict, bytes]:  # pragma: no cover
        raise NotImplementedError

    def cand(self, **kw) -> dict:
        return {"source": self.name, "licence": self.licence, **kw}


class Pixabay(Adapter):
    name, needs_key, credit, gap_s = "pixabay", "pixabay", "PIXABAY", 1.0
    licence = "Pixabay Content License"
    licence_url = "https://pixabay.com/service/license-summary/"
    licence_text = "licences/pixabay-content-license-summary.txt"
    terms_url = "https://pixabay.com/api/docs/"
    terms_text = "licences/pixabay-api-terms-excerpt.txt"

    def _q(self, params: str, name: str) -> dict:
        key = key_for("pixabay")
        return _cached(f"pixabay-{name}", lambda: json.loads(_get(
            f"https://pixabay.com/api/videos/?safesearch=true&key={key}&{params}", gap=self.gap_s)))

    @staticmethod
    def rendition(h: dict) -> dict | None:
        """The 1920 rendition, else the 1280 one (Pixabay's large/medium/small
        are 3840/2560/1280 for a 4K upload, 1920/1280/960 for an HD one)."""
        best = None
        for size in ("large", "medium", "small"):
            f = (h.get("videos") or {}).get(size) or {}
            w = f.get("width") or 0
            if f.get("url") and 1280 <= w <= 1920 and (not best or w > best["width"]):
                best = f
        return best

    def search(self, query: str) -> list[dict]:
        js = self._q("per_page=50&q=" + urllib.parse.quote(query), f"q-{query}")
        out = []
        for h in js.get("hits") or []:
            # Real footage only: Pixabay labels generated video (isAiGenerated)
            # and separates filmed "film" from "animation" (CG / generated).
            if h.get("isAiGenerated") or h.get("type") != "film":
                continue
            f = self.rendition(h)
            if f:
                out.append(self.cand(id=str(h["id"]), item_url=h["pageURL"],
                                     title=h.get("tags") or "", duration=h.get("duration"),
                                     width=f.get("width"), author=h.get("user")))
        return out

    def download(self, cand: dict) -> tuple[dict, bytes]:
        hits = self._q(f"id={int(cand['id'])}", f"id-{cand['id']}").get("hits") or []
        if not hits:
            raise ValueError(f"Pixabay video {cand['id']} not found")
        if hits[0].get("isAiGenerated") or hits[0].get("type") != "film":
            raise ValueError(f"Pixabay {cand['id']} is {hits[0].get('type')!r}/AI - not real footage")
        f = self.rendition(hits[0])
        if not f:
            raise ValueError("no 1280-1920 rendition")
        return ({"download_url": f["url"].split("?")[0], "source_org": hits[0].get("user") or "Pixabay",
                 "licence_basis": "Pixabay Content License: API result for this id"},
                _get(f["url"], binary=True, gap=self.gap_s))


class Pexels(Adapter):
    name, needs_key, credit = "pexels", "pexels", "PEXELS"
    licence = "Pexels License"
    licence_url = "https://www.pexels.com/license/"
    terms_url = "https://www.pexels.com/api/documentation/"

    def _q(self, url: str, name: str) -> dict:
        key = key_for("pexels")
        return _cached(f"pexels-{name}", lambda: json.loads(
            _get(url, gap=self.gap_s, headers={"Authorization": key})))

    @staticmethod
    def rendition(v: dict) -> dict | None:
        files = [f for f in v.get("video_files") or []
                 if f.get("file_type") == "video/mp4" and 1280 <= (f.get("width") or 0) <= 1920]
        return max(files, key=lambda f: f["width"]) if files else None

    def search(self, query: str) -> list[dict]:
        js = self._q("https://api.pexels.com/videos/search?per_page=40&query="
                     + urllib.parse.quote(query), f"q-{query}")
        out = []
        for v in js.get("videos") or []:
            f = self.rendition(v)
            if f:
                out.append(self.cand(id=str(v["id"]), item_url=v["url"],
                                     title=v["url"].rstrip("/").split("/")[-1],
                                     duration=v.get("duration"), width=f["width"],
                                     author=(v.get("user") or {}).get("name")))
        return out

    def download(self, cand: dict) -> tuple[dict, bytes]:
        v = self._q(f"https://api.pexels.com/videos/videos/{int(cand['id'])}", f"id-{cand['id']}")
        f = self.rendition(v)
        if not f:
            raise ValueError("no 1280-1920 rendition")
        return ({"download_url": f["link"] if "link" in f else f["url"],
                 "source_org": (v.get("user") or {}).get("name") or "Pexels",
                 "licence_basis": "Pexels License: API result for this id"},
                _get(f.get("link") or f["url"], binary=True, gap=self.gap_s))


class Mixkit(Adapter):
    name, credit, gap_s = "mixkit", "MIXKIT", MIXKIT_GAP_S
    licence = "Mixkit Stock Video Free License"
    licence_url = "https://mixkit.co/license/#videoFree"
    licence_text = "licences/mixkit-stock-video-free-license.txt"
    terms_url = "https://mixkit.co/terms/"
    terms_text = "licences/mixkit-user-terms-restrictions.txt"

    @staticmethod
    def licence_ok(page: str) -> tuple[bool, str]:
        """The item page itself must put the download under the FREE video licence."""
        if 'data-license="videoRestricted"' in page:
            return False, "item page marks it Stock Video Restricted License"
        if 'data-license="videoFree"' not in page or "Mixkit Stock Video Free License" not in page:
            return False, "item page does not state the Mixkit Stock Video Free License"
        return True, "item page states 'Mixkit Stock Video Free License' for this download"

    def search(self, query: str) -> list[dict]:
        slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
        page = _cached(f"mixkit-{slug}", lambda: _get(
            f"https://mixkit.co/free-stock-video/{slug}/", gap=self.gap_s))
        out, seen = [], set()
        for m in re.finditer(r'href="/free-stock-video/([a-z0-9-]+)-(\d+)/"', page):
            if m.group(2) in seen:
                continue
            seen.add(m.group(2))
            out.append(self.cand(id=m.group(2), title=m.group(1).replace("-", " "),
                                 item_url=f"https://mixkit.co/free-stock-video/{m.group(1)}-{m.group(2)}/",
                                 duration=None, width=1920, author="Mixkit"))
        return out

    def download(self, cand: dict) -> tuple[dict, bytes]:
        page = _get(cand["item_url"], gap=self.gap_s)
        ok, why = self.licence_ok(page)
        if not ok:
            raise ValueError(why)
        vid = cand["id"]
        for res in ("1080", "720"):
            url = f"https://assets.mixkit.co/videos/{vid}/{vid}-{res}.mp4"
            try:
                return ({"download_url": url, "source_org": "Mixkit", "licence_basis": why},
                        _get(url, binary=True, gap=self.gap_s))
            except Exception:                                 # noqa: BLE001
                continue
        raise ValueError("no 1080p or 720p file")


class Coverr(Adapter):
    name, credit = "coverr", "COVERR"
    licence = "Coverr License"
    licence_url = "https://coverr.co/license"
    licence_text = "licences/coverr-license-excerpt.txt"
    terms_url = "https://coverr.co/terms"
    terms_text = "licences/coverr-terms-excerpt.txt"
    terms_block = ("Website Terms forbid access 'through ... robots, or any other automated means "
                   "or data gathering and extraction tools'; the API needs a key "
                   "(licences/coverr-terms-excerpt.txt)")

    def search(self, query: str) -> list[dict]:
        raise PermissionError(self.terms_block)

    download = search


class Commons(Adapter):
    name, credit, gap_s = "commons", "", 3.0
    licence = "Public domain / CC0 (per item, read live)"
    licence_url = "https://commons.wikimedia.org/wiki/Commons:Licensing"
    terms_url = "https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use"

    def _info(self, titles: list[str]) -> list[dict]:
        q = ("https://commons.wikimedia.org/w/api.php?action=query&format=json&prop=imageinfo"
             "&iiprop=url|size|mime|extmetadata&titles=" + urllib.parse.quote("|".join(titles)))
        pages = json.loads(_get(q, gap=self.gap_s))["query"]["pages"].values()
        return [{**p["imageinfo"][0], "title": p["title"]} for p in pages if p.get("imageinfo")]

    def search(self, query: str) -> list[dict]:
        sys.path.insert(0, str(HERE))
        import imagery as I                                     # noqa: PLC0415

        def fetch():
            q = ("https://commons.wikimedia.org/w/api.php?action=query&list=search&srnamespace=6"
                 "&srlimit=30&format=json&srsearch=" + urllib.parse.quote(query + " filetype:video"))
            titles = [x["title"] for x in json.loads(_get(q, gap=self.gap_s))["query"]["search"]]
            out = []
            for k in range(0, len(titles), 20):
                for info in self._info(titles[k:k + 20]):
                    ok, why = I.pd_licence_ok(info)
                    if ok and (info.get("width") or 0) >= 640:
                        lic = re.sub(r"<[^>]+>", "", str(info["extmetadata"]["LicenseShortName"]["value"])).strip()
                        out.append({"title": info["title"], "item_url": info.get("descriptionurl"),
                                    "duration": info.get("duration"), "width": info.get("width"),
                                    "licence": lic})
            return out
        return [self.cand(id=c["title"], **{k: v for k, v in c.items()}) | {"licence": c["licence"]}
                for c in _cached(f"commons-{query}", fetch)]

    def download(self, cand: dict) -> tuple[dict, bytes]:
        sys.path.insert(0, str(HERE))
        import imagery as I                                     # noqa: PLC0415
        import imagery_materials as M                           # noqa: PLC0415
        info = self._info([cand["id"]])[0]
        ok, why = I.pd_licence_ok(info)
        if not ok:
            raise ValueError(why)
        claimed, why_c = M.copyright_asserted(info)
        if claimed:
            raise ValueError(why_c)
        src = info["url"].split("?")[0]
        artist = re.sub(r"\s+", " ", M._text(info, "Artist")).strip()
        return ({"download_url": src, "source_org": artist or "Wikimedia Commons",
                 "licence_basis": why}, _get(src, binary=True, gap=self.gap_s))


class InternetArchive(Adapter):
    name, credit = "archive", ""
    licence = "Public domain (Internet Archive licenseurl)"
    licence_url = "https://archive.org/details/prelinger"
    terms_url = "https://archive.org/about/terms.php"
    COLLECTIONS = ("prelinger", "FedFlix")
    PD_URL = re.compile(r"creativecommons\.org/(licenses/publicdomain|publicdomain/(zero|mark))")

    def search(self, query: str) -> list[dict]:
        cols = " OR ".join(f"collection:{c}" for c in self.COLLECTIONS)
        q = f"({query}) AND mediatype:movies AND ({cols})"
        url = ("https://archive.org/advancedsearch.php?output=json&rows=30&fl[]=identifier"
               "&fl[]=title&fl[]=licenseurl&fl[]=collection&q=" + urllib.parse.quote(q))
        docs = _cached(f"archive-{query}", lambda: json.loads(_get(url, gap=self.gap_s))["response"]["docs"])
        return [self.cand(id=d["identifier"], title=str(d.get("title") or ""),
                          item_url=f"https://archive.org/details/{d['identifier']}",
                          duration=None, width=None, licence=d["licenseurl"], author="Internet Archive")
                for d in docs if self.PD_URL.search(str(d.get("licenseurl") or ""))]

    def download(self, cand: dict) -> tuple[dict, bytes]:
        meta = json.loads(_get(f"https://archive.org/metadata/{cand['id']}", gap=self.gap_s))
        lic = (meta.get("metadata") or {}).get("licenseurl") or ""
        if not self.PD_URL.search(lic):
            raise ValueError(f"licenseurl {lic!r} is not a PD/CC0 URL")
        mp4 = [f for f in meta.get("files") or [] if f["name"].lower().endswith(".mp4")]
        if not mp4:
            raise ValueError("no mp4 derivative")
        f = max(mp4, key=lambda f: int(f.get("size") or 0))
        url = f"https://archive.org/download/{cand['id']}/{urllib.parse.quote(f['name'])}"
        return ({"download_url": url, "source_org": "Internet Archive",
                 "licence_basis": f"item licenseurl {lic}", "licence": "Public domain"},
                _get(url, binary=True, gap=self.gap_s))


class Nasa(Adapter):
    name, credit = "nasa", "NASA"
    licence = "Public domain (NASA, US government work)"
    licence_url = "https://www.nasa.gov/nasa-brand-center/images-and-media/"
    terms_url = "https://images.nasa.gov/"

    def search(self, query: str) -> list[dict]:
        url = "https://images-api.nasa.gov/search?media_type=video&q=" + urllib.parse.quote(query)
        items = _cached(f"nasa-{query}", lambda: json.loads(_get(url, gap=self.gap_s))["collection"]["items"])
        out = []
        for it in items[:30]:
            d = (it.get("data") or [{}])[0]
            if (d.get("center") or "") and "copyright" not in json.dumps(d).lower():
                out.append(self.cand(id=d["nasa_id"], title=d.get("title") or "",
                                     item_url=f"https://images.nasa.gov/details/{d['nasa_id']}",
                                     duration=None, width=None, author=d.get("center")))
        return out

    def download(self, cand: dict) -> tuple[dict, bytes]:
        files = json.loads(_get(f"https://images-api.nasa.gov/asset/{urllib.parse.quote(cand['id'])}",
                                gap=self.gap_s))["collection"]["items"]
        mp4 = [f["href"] for f in files if f["href"].endswith(".mp4")]
        pick = next((u for u in mp4 if "~orig" in u), mp4[0] if mp4 else None)
        if not pick:
            raise ValueError("no mp4")
        return ({"download_url": pick, "source_org": "NASA",
                 "licence_basis": "NASA media: US government work, no copyright"},
                _get(pick, binary=True, gap=self.gap_s))


CHAIN: list[Adapter] = [Pixabay(), Pexels(), Mixkit(), Coverr(), Commons(), InternetArchive(), Nasa()]
BY_NAME = {a.name: a for a in CHAIN}
FALLBACKS = [a.name for a in CHAIN[1:]]


def sources_status() -> dict:
    return {a.name: a.enabled()[1] for a in CHAIN}


# ------------------------------------------------------------ the shot list
# The chocolate segment's needs. `query` is searched in every adapter; a
# candidate must contain one word of EACH group in `must` (title/tags), and no
# BANNED_WORDS. One distinct clip per need.
SHOTS: list[dict] = [
    {"need": "pour-dark", "query": "melted chocolate", "label": "MELTED CHOCOLATE",
     "must": [["chocolate"], ["melt", "liquid", "flow", "pour"]], "uses": ["pour", "liquid", "melt"],
     "sound": "pour", "basis": "Melted chocolate poured in a stream: chocolate above its melting point."},
    {"need": "sheets", "query": "chocolate fountain", "label": "MELTED CHOCOLATE",
     "must": [["chocolate"], ["fountain", "texture"]], "uses": ["sheets", "liquid", "melt", "scale"],
     "sound": "pour", "basis": "Chocolate falling in a continuous sheet."},
    {"need": "fountain-flow", "query": "chocolate fountain", "label": "MELTED CHOCOLATE",
     "must": [["chocolate"], ["fountain", "flowing", "flow"]], "uses": ["pour", "liquid", "melt"],
     "sound": "pour", "basis": "Liquid chocolate flowing down a fountain."},
    {"need": "splash", "query": "chocolate splash", "label": "LIQUID CHOCOLATE",
     "must": [["chocolate"], ["splash", "falling", "drop"]], "uses": ["liquid", "melt", "drip"],
     "sound": "pour", "basis": "A drop falling into liquid chocolate and splashing."},
    {"need": "stream", "query": "chocolate pouring", "label": "LIQUID CHOCOLATE",
     "must": [["chocolate"], ["pour", "syrup", "stream"]], "uses": ["pour", "liquid"],
     "sound": "pour", "basis": "A thin stream of liquid chocolate poured and pooling."},
    {"need": "drip-strawberry", "query": "chocolate strawberry", "label": "LIQUID CHOCOLATE",
     "must": [["chocolate"], ["strawberr"]], "uses": ["drip", "coat", "liquid", "temper"],
     "sound": "pour", "basis": "Liquid chocolate running over fruit: a melt about to set into a shell."},
    {"need": "coat", "query": "chocolate syrup", "label": "LIQUID CHOCOLATE",
     "must": [["chocolate"], ["covering", "cover", "coat", "syrup", "sauce"]], "uses": ["drip", "coat", "liquid"],
     "sound": "pour", "basis": "Chocolate coating a surface and dripping off it."},
    {"need": "drip-macro", "query": "chocolate dripping", "label": "LIQUID CHOCOLATE",
     "must": [["chocolate"], ["drip", "texture", "covered", "melted"]], "uses": ["drip", "liquid", "melt"],
     "sound": "pour", "basis": "Chocolate dripping in close-up: the liquid phase."},
    {"need": "chunks", "query": "chocolate pieces", "label": "CHOCOLATE",
     "must": [["chocolate"], ["chunk", "piece", "pile", "bar"]], "uses": ["bar", "snap", "solid", "crystal"],
     "sound": "snap", "basis": "Broken pieces of solid chocolate: the set, snapping solid."},
    {"need": "chunks-macro", "query": "chocolate bar", "label": "CHOCOLATE",
     "must": [["chocolate"], ["chunk", "texture", "bar"]], "uses": ["bar", "solid", "crystal", "gloss"],
     "sound": None, "basis": "Close texture of broken chocolate: the glossy crystalline break."},
    {"need": "pile", "query": "chocolate candy", "label": "CHOCOLATE",
     "must": [["chocolate"], ["candy", "beans", "praline", "sweets", "rotating"]], "uses": ["solid", "scale"],
     "sound": None, "basis": "A heap of chocolates: solid chocolate at scale."},
    {"need": "beans", "query": "chocolate candy", "label": "CHOCOLATE",
     "must": [["chocolate"], ["beans", "candy", "rotating", "praline"]], "uses": ["solid", "scale"],
     "sound": None, "basis": "A field of chocolate pieces turning slowly."},
    {"need": "field", "query": "chocolate candy", "label": "CHOCOLATE",
     "must": [["chocolate"], ["beans", "rotating"]], "uses": ["solid", "scale"],
     "sound": None, "basis": "Chocolate pieces filling the frame, turning: a field of them."},
    {"need": "bite", "query": "eating chocolate", "label": "CHOCOLATE",
     "must": [["chocolate"], ["biting", "bite", "eating"]], "uses": ["mouth", "bite"],
     "sound": "snap", "basis": "A bite into chocolate: 'melts in your mouth'."},
    {"need": "cacao", "query": "cacao", "label": "CACAO",
     "must": [["cacao", "cocoa"]], "uses": ["cacao", "cocoa", "process", "beans"],
     "sound": None,
     # the VOA report's cacao footage (pods on the tree, beans drying, hands in
     # the beans); the interviews, the fertiliser shed and the captions are not used
     "ranges": {"commons:File:Production de cacao ivorienne VOA 01000000-0aff-0242-01e6-08db257d93df 720p.webm":
                [[19.8, 22.5], [85.6, 88.0], [82.4, 85.3], [44.0, 49.3], [53.5, 57.7],
                 [202.5, 207.5], [39.6, 43.6], [0.3, 9.6]]},
     # scene cuts measured with ffmpeg scdet; the crop keeps VOA's corner logo out of frame
     # (the credit line names Voice of America on screen instead)
     "crop": {"commons:File:Production de cacao ivorienne VOA 01000000-0aff-0242-01e6-08db257d93df 720p.webm":
              [0.12, 0.0, 0.88, 0.86]},
     "basis": "Cacao farming: pods and beans, where cocoa butter comes from."},
]
for _s in SHOTS:
    _s.setdefault("segment", "chocolate")


def _shot(segment: str, need: str, query: str, label: str, must: list[list[str]],
          uses: list[str], basis: str, sound: str | None = None) -> dict:
    return {"segment": segment, "need": need, "query": query, "label": label, "must": must,
            "uses": uses, "sound": sound, "basis": basis}


# The sound layer's cue per bread/steak need (visuals/food_sound): crackle for a
# crust being cut or beans roasting, a fire's crackle under flames and coals,
# grain and flour falling under the pour cue; wheat in the wind gets none.
SOUND_FOR = {
    "bread-buns": "snap", "bread-display": "snap", "bread-loaf-knife": "snap", "bread-slice": "snap",
    "bread-oven-fire": "sizzle", "bread-flour-sift": "pour", "bread-flour-mill": "pour",
    "bread-mixer": "pour", "bread-flour-dough": "pour",
    "steak-fire": "sizzle", "steak-coals": "sizzle", "steak-coffee": "snap", "steak-toast": "snap",
}


# The first full video (owner, 13 Oct 2026: "Bread, Steak, Chocolate: What's
# Inside?") adds a bread and a steak segment: >= MIN_REAL_CLIPS real clips each,
# through the same chain, the same gates, the same licence record. The owner's
# standing preference the same day - LIMIT HUMAN HANDS, "not bad if we do
# sometimes" - is a pick order (clips without hands are reviewed first) and a
# measured share (HANDS below; visuals/food.py screen_time), not a ban.
SHOTS += [
    # ---- bread
    _shot("bread", "bread-rise-oven", "oven", "BREAD", [["bread"], ["rising", "growing"]],
          ["rise", "oven", "loaf", "bake"], "A loaf rising inside the oven: oven spring, filmed."),
    {**_shot("bread", "bread-grow-oven", "oven", "BREAD", [["bread"], ["growing", "rising"]],
             ["rise", "dough", "bake"], "Proved dough balls on a baking tray: risen dough, filmed."),
     # the first 5.5 s show the baker's hand shaping a ball; only the tray is used
     "ranges": {"pixabay:42040": [[6.0, 15.5]]}},
    _shot("bread", "bread-mixer", "dough", "DOUGH", [["dough"], ["mixer", "industrial"]],
          ["dough", "stretch", "knead", "scale"], "An industrial mixer working dough: gluten being lined up."),
    _shot("bread", "bread-knead", "dough", "DOUGH", [["dough"], ["kneading", "knead"]],
          ["knead", "dough", "stretch"], "Dough kneaded by hand: the gluten network strengthened."),
    _shot("bread", "bread-flour-dough", "dough", "DOUGH", [["dough"], ["flour", "sprinkling"]],
          ["dough", "flour"], "Flour on fresh dough."),
    _shot("bread", "bread-wheat-field", "wheat", "WHEAT", [["wheat"], ["field", "swaying", "golden"]],
          ["wheat", "flour", "scale"], "A field of wheat moving in the wind: where the flour starts."),
    _shot("bread", "bread-wheat-close", "wheat", "WHEAT", [["wheat"], ["close", "tops", "crop"]],
          ["wheat", "flour"], "Ears of wheat close up."),
    _shot("bread", "bread-harvest", "wheat", "WHEAT", [["wheat", "mower"], ["harvest"]],
          ["wheat", "scale"], "Wheat harvested at field scale."),
    _shot("bread", "bread-flour-mill", "flour", "FLOUR", [["flour"], ["stone", "rotating", "mill"]],
          ["flour", "wheat"], "Wheat ground to flour between turning stones."),
    _shot("bread", "bread-flour-sift", "flour", "FLOUR", [["flour"], ["sifting", "sieve"]],
          ["flour"], "Flour falling through a sieve in slow motion."),
    _shot("bread", "bread-buns", "bread", "BREAD", [["bread"], ["bun", "buns"]],
          ["loaf", "crust", "bake"], "Baked bread rolls: the browned crust."),
    _shot("bread", "bread-loaf-knife", "bread", "BREAD", [["bread"], ["knife", "loaf"]],
          ["slice", "crumb", "loaf"], "A loaf cut open: the crumb and its holes."),
    _shot("bread", "bread-slice", "bread", "BREAD", [["bread"], ["slice", "cut"]],
          ["slice", "crumb"], "Bread sliced: the holes the gas left."),
    _shot("bread", "bread-oven-fire", "bread oven", "BREAD", [["bread", "oven"], ["fire", "flame"]],
          ["oven", "bake", "crust"], "The fire of a bread oven: the heat that sets the crumb."),
    _shot("bread", "bread-loaf-oven", "bread oven", "BREAD", [["bread", "loaf"], ["oven"]],
          ["oven", "loaf", "bake", "crust"], "Loaves in an oven."),
    _shot("bread", "bread-display", "bakery", "BREAD", [["baked", "bakery"], ["display", "goods"]],
          ["loaf", "scale", "crust"], "Rows of baked goods: bread at scale."),
    _shot("bread", "bread-microscope", "microscope", "MICROSCOPE", [["microscope"], ["lab", "close"]],
          ["micro", "lab"], "A laboratory microscope: the instrument that showed yeast is alive."),
    _shot("bread", "bread-lab", "laboratory", "LABORATORY", [["lab", "laboratory"], ["tube", "drops", "dropper"]],
          ["lab"], "Laboratory glass: measurement, not tasting."),
    # ---- steak
    _shot("steak", "steak-sear-grill", "steak", "STEAK", [["steak"], ["seared", "sizzling", "fiery"]],
          ["sear", "grill", "flame", "sizzle", "crust", "meat"], "A steak seared on a hot grill: the Maillard crust forming.", "sizzle"),
    _shot("steak", "steak-slowmo", "steak", "STEAK", [["steak"], ["slow motion", "grill"]],
          ["grill", "sear", "meat"], "A steak on the grill in slow motion.", "sizzle"),
    _shot("steak", "steak-sizzle", "steak", "STEAK", [["steak"], ["sizzling", "close"]],
          ["sear", "sizzle", "crust"], "A sizzling steak close up: the browned surface.", "sizzle"),
    _shot("steak", "steak-flame", "steak", "STEAK", [["steak"], ["flame", "barbeque", "barbecue"]],
          ["flame", "grill", "char"], "Steak over flames.", "sizzle"),
    _shot("steak", "steak-butter", "steak", "STEAK", [["steak"], ["butter"]],
          ["butter", "fat", "sizzle"], "Butter melting on a hot steak: fat at work.", "sizzle"),
    _shot("steak", "steak-grill-sit", "steak", "STEAK", [["steak"], ["grill", "grilled"]],
          ["grill", "crust", "meat"], "A grilled steak resting on the grill.", "sizzle"),
    _shot("steak", "steak-tenderloin", "barbecue", "BEEF", [["beef", "tenderloin"], ["seared", "grill"]],
          ["sliced", "inside", "crust", "sear", "meat"],
          "Seared beef sliced: the pale interior under the thin brown crust."),
    _shot("steak", "steak-bbq", "grill", "STEAK", [["steak", "meat"], ["bbq", "grill", "roasting"]],
          ["grill", "meat", "scale"], "Meat on a barbecue grill.", "sizzle"),
    _shot("steak", "steak-roast", "grill", "MEAT", [["meat"], ["roasting", "grill"]],
          ["grill", "meat", "crust"], "Browned, roasted meats: the Maillard crust on many cuts."),
    _shot("steak", "steak-fire", "grill", "GRILL", [["flames", "fire"], ["grill", "bbq", "brazier"]],
          ["flame", "char"], "Flames inside a grill: the heat source, and what charring is."),
    _shot("steak", "steak-coals", "grill", "GRILL", [["carbon", "coal", "coals"], ["flames", "brazier"]],
          ["flame", "char"], "Coals burning: heat without fire on the meat."),
    _shot("steak", "steak-pan", "meat", "BEEF", [["meat"], ["frying", "pan"]],
          ["meat", "raw", "beef"], "Raw beef cut into pieces: the meat before any browning."),
    _shot("steak", "steak-fry", "steak", "MEAT", [["meat"], ["frying", "piece"]],
          ["pan", "sear", "sizzle", "fat"], "A piece of meat frying close up.", "sizzle"),
    _shot("steak", "steak-skewers", "meat", "MEAT", [["meat"], ["skewers"]],
          ["grill", "scale", "meat"], "Skewers of meat grilling.", "sizzle"),
    _shot("steak", "steak-seasoned", "barbecue", "STEAK", [["steak"], ["seasoned"]],
          ["grill", "sear"], "A seasoned steak on the grill.", "sizzle"),
    _shot("steak", "steak-sliced", "steak", "STEAK", [["steak"], ["sliced", "knife"]],
          ["sliced", "inside", "crust"], "A cooked steak sliced: the pale interior inside the brown crust."),
    _shot("steak", "steak-coffee", "coffee roasting", "COFFEE", [["coffee"], ["roasting", "roasted"]],
          ["coffee", "roast"], "Coffee beans roasting: the same browning reaction."),
    _shot("steak", "steak-toast", "toast", "TOAST", [["toast", "toaster"], ["bread", "toaster"]],
          ["toast", "bread"], "Bread toasting: the same browning reaction."),
    _shot("steak", "steak-lab", "laboratory", "LABORATORY", [["lab"], ["tubes", "dropper", "drops"]],
          ["lab"], "Laboratory glassware: the chemistry of a smell, measured."),
]
for _s in SHOTS:
    if _s["need"] in SOUND_FOR:
        _s["sound"] = SOUND_FOR[_s["need"]]

# Looked at and refused, with the reason (source:id -> why).
REFUSED: dict[str, str] = {
    "pixabay:307248": "Pixabay marks it AI-generated (type animation)",
    "pixabay:98283": "its uploader tags it '3d': it may be a render, and only filmed footage is allowed",
    "pixabay:326912": "Pixabay type 'animation': generated, not filmed",
    "mixkit:22920": "its item page puts it under the Stock Video RESTRICTED License (gate caught it)",
    "pixabay:250784": "the same shot as pixabay:43653 (uploaded twice); one copy is enough",
    "pixabay:82789": "roast chicken with peppers, not a seared steak",
    "pixabay:11602": "hands working raw meat in flour, not a cooked steak sliced open",
    "pixabay:4403": "people at a barbecue; the meat is a corner of the frame",
    "mixkit:50956": "smoke on black: after the grade it reads as an empty black frame (first full render, 13 Oct 2026)",
    "mixkit:6948": "its item page puts it under the Stock Video RESTRICTED License (gate caught it, 13 Oct 2026)",
    "mixkit:6787": "its item page puts it under the Stock Video RESTRICTED License (gate caught it, 13 Oct 2026)",
    "mixkit:48057": "its item page puts it under the Stock Video RESTRICTED License (gate caught it, 13 Oct 2026)",
    "mixkit:21057": "its item page puts it under the Stock Video RESTRICTED License (gate caught it, 13 Oct 2026)",
    "mixkit:27143": "its item page puts it under the Stock Video RESTRICTED License (gate caught it, 13 Oct 2026)",
    "mixkit:48053": "its item page puts it under the Stock Video RESTRICTED License (gate caught it, 13 Oct 2026)",
    "mixkit:21927": "its item page puts it under the Stock Video RESTRICTED License (gate caught it, 13 Oct 2026)",
    "mixkit:45724": "its item page puts it under the Stock Video RESTRICTED License (gate caught it, 13 Oct 2026)",
    "mixkit:31741": "its item page puts it under the Stock Video RESTRICTED License (gate caught it, 13 Oct 2026)",
    "mixkit:22774": "its item page puts it under the Stock Video RESTRICTED License (gate caught it, 13 Oct 2026)",
    "mixkit:45718": "its item page puts it under the Stock Video RESTRICTED License (gate caught it, 13 Oct 2026)",
    "mixkit:17556": "its item page puts it under the Stock Video RESTRICTED License (gate caught it, 13 Oct 2026)",
    "pixabay:55580": "a CG render of chocolate gears, not footage",
    "pixabay:186709": "a recognisable brand (Nutella) - Pixabay licence bars branded commercial use",
    "pixabay:71745": "red sauce, not chocolate",
    "pixabay:149477": "a person in bed; the chocolate is incidental",
    "pixabay:200250": "a person; the chocolate is incidental",
    "pixabay:62051": "a recognisable brand (Snickers)",
    "pixabay:94567": "a CG render on a rainbow background",
    "mixkit:26597": "a busy breakfast flat-lay; the chocolate is a corner of it",
    "mixkit:10371": "pastel ice cream; not chocolate in motion",
    "mixkit:52207": "chocolate cereal, not chocolate",
    "mixkit:52208": "chocolate cereal, not chocolate",
    "mixkit:41110": "cupcakes; the drizzle is barely visible",
    "mixkit:41119": "cupcakes; the drizzle is barely visible",
    **{f"pixabay:{i}": "a fruit-and-cake plate; tagged cocoa, shows no cacao"
       for i in (80331, 80332, 80333, 80334, 80335, 80336, 80338)},
}


# Looked at (contact sheets of every candidate, 2026-10-13) and chosen, best
# first, per need. The chain still decides the ORDER of sources; inside a source
# a reviewed pick goes first, and an unreviewed candidate is taken only on a
# strict match (its subject words lead its tags/title).
PREFER: dict[str, list[str]] = {
    "pour-dark": ["mixkit:41109"],
    "sheets": ["mixkit:41126"],
    "fountain-flow": ["mixkit:41112"],
    "stream": ["mixkit:41109"],
    "drip-strawberry": ["pixabay:71743", "mixkit:41125"],
    "coat": ["mixkit:41115", "mixkit:41125"],
    "drip-macro": ["mixkit:41108"],
    "chunks": ["mixkit:41117"],
    "chunks-macro": ["mixkit:41121"],
    "pile": ["pixabay:12669", "mixkit:40797"],
    "beans": ["mixkit:40797", "pixabay:71747"],
    "field": ["mixkit:40797"],
    "bite": ["mixkit:10373"],
    "cacao": ["commons:File:Production de cacao ivorienne VOA 01000000-0aff-0242-01e6-08db257d93df 720p.webm"],
}
PREFER.update({
    "bread-rise-oven": ["pixabay:250784"],
    "bread-grow-oven": ["pixabay:42040"],
    "bread-mixer": ["pixabay:65278"],
    "bread-knead": ["mixkit:42467"],
    "bread-flour-dough": ["pixabay:75700"],
    "bread-wheat-field": ["mixkit:25915", "mixkit:17120", "pixabay:17285"],
    "bread-wheat-close": ["mixkit:21531", "mixkit:17427"],
    "bread-harvest": ["mixkit:45782", "mixkit:23781"],
    "bread-flour-mill": ["pixabay:784"],
    "bread-flour-sift": ["pixabay:292737"],
    "bread-buns": ["pixabay:207994", "pixabay:207992"],
    "bread-loaf-knife": ["pixabay:63066", "pixabay:14239"],
    "bread-slice": ["pixabay:209418"],
    "bread-oven-fire": ["pixabay:107899"],
    "bread-loaf-oven": ["pixabay:205890"],
    "bread-display": ["pixabay:207992"],
    "bread-microscope": ["pixabay:86260", "pixabay:86259"],
    "bread-lab": ["pixabay:197483"],
    "steak-sear-grill": ["mixkit:45723"],
    "steak-slowmo": ["mixkit:46660"],
    "steak-sizzle": ["mixkit:45716", "pixabay:11632"],
    "steak-flame": ["mixkit:45728"],
    "steak-butter": ["pixabay:72000"],
    "steak-grill-sit": ["mixkit:45722", "pixabay:16406"],
    "steak-tenderloin": ["mixkit:45717"],
    "steak-bbq": ["pixabay:127253", "mixkit:2774"],
    "steak-roast": ["mixkit:2993"],
    "steak-fire": ["mixkit:2780"],
    "steak-coals": ["mixkit:6969", "pixabay:127250"],
    "steak-pan": ["pixabay:208479", "mixkit:46673"],
    "steak-fry": ["mixkit:46663", "pixabay:208354"],
    "steak-skewers": ["pixabay:4403"],
    "steak-seasoned": ["pixabay:16373"],
    "steak-sliced": ["pixabay:11602"],
    "steak-coffee": ["mixkit:24762", "pixabay:71288"],
    "steak-toast": ["pixabay:199970"],
    "steak-lab": ["pixabay:76396"],
})
# HUMAN HANDS (owner, 13 Oct 2026): "limit human hands" - not a ban ("not bad
# if we do sometimes"). Reviewed on contact sheets: need -> (hands visible, why).
# A clip not listed falls back to its own words (HAND_WORDS). visuals/food.py
# measures hands-visible screen time per render and per episode.
HAND_WORDS = ("hand", "hands", "chef", "cook ", "baker", "kneading", "woman", "man ",
              "person", "girl", "boy", "mom", "biting", "eating", "cutting", "slicing")
HANDS: dict[str, tuple[bool, str]] = {
    # chocolate (round-2 sample)
    "bite": (True, "a woman's hand lifts the chocolate to her mouth"),
    "cacao": (True, "the VOA ranges include hands in the drying beans"),
    # bread - contact sheets 2026-10-13
    "bread-buns": (True, "a hand holds the roll while a knife cuts it"),
    "bread-display": (True, "hands cut a baguette on a board"),
    "bread-flour-dough": (True, "a hand rolls the dough at the end"),
    "bread-flour-sift": (True, "a hand taps the sieve"),
    "bread-knead": (True, "a hand presses the dough"),
    "bread-lab": (True, "a gloved hand holds the flask"),
    "bread-loaf-knife": (True, "hands slice the loaf"),
    "bread-slice": (True, "hands slice the loaf"),
    "bread-grow-oven": (False, "only the tray of risen dough is used (ranges skip the hand)"),
    "bread-flour-mill": (False, "windmill sails and falling grain, no person"),
    "bread-harvest": (False, "wheat against the sun"),
    "bread-loaf-oven": (False, "dough on a sheeter belt, no person"),
    "bread-microscope": (False, "a face at the eyepiece; no hands in frame"),
    "bread-mixer": (False, "flour heap and rolling pin, no hands"),
    "bread-oven-fire": (False, "fire in a bread oven"),
    "bread-wheat-close": (False, "wheat"),
    "bread-wheat-field": (False, "wheat"),
    # steak - contact sheets 2026-10-13
    "steak-fry": (True, "a hand with tongs at the edge of frame"),
    "steak-lab": (True, "a gloved hand at the rack"),
    "steak-pan": (True, "hands cut raw beef"),
    "steak-slowmo": (True, "tongs and the hand holding them lower the steak"),
    "steak-bbq": (False, "a steak searing in a pan"),
    "steak-butter": (False, "steaks in a pan"),
    "steak-coals": (False, "a steak over coals"),
    "steak-coffee": (False, "coffee beans before flames"),
    "steak-fire": (False, "a wood fire"),
    "steak-flame": (False, "a rib steak on the grill"),
    "steak-grill-sit": (False, "meat browning in a pan"),
    "steak-sear-grill": (False, "a steak on a grill pan"),
    "steak-seasoned": (False, "tongs over coals, no hand in frame"),
    "steak-sizzle": (False, "beef and peppers on a sizzling plate"),
    "steak-tenderloin": (False, "sliced seared beef on a plate"),
    "steak-toast": (False, "a toaster"),
    "steak-roast": (False, "browned roast meats on a board"),
}
OFF_SUBJECT = ("beach", "commission", "puffs", "drugslab", "smoothie", "conference", "coffee",
               "latte", "ice cream", "waffle", "cereal", "cupcake", "donut", "cake", "milk",
               "easter", "girl", "woman", "man ", "couple")


def _head(c: dict) -> str:
    """The words that say what a clip IS: a tag list's first tag, else the title."""
    t = str(c.get("title") or "").lower()
    return t.split(", ")[0] if t.count(",") >= 2 else t


def strict(c: dict, shot: dict) -> bool:
    h = _head(c)
    return (any(w in h for w in shot["must"][0]) and not any(w in h for w in OFF_SUBJECT)
            and matches(c, shot))


def _text(c: dict) -> str:
    return f"{c.get('title') or ''} {c.get('item_url') or ''}".lower()


def banned(c: dict) -> bool:
    """Generated, drawn or branded by its own words - refused even when hand-picked."""
    t = _text(c)
    return any(re.search(rf"(^|[^a-z]){re.escape(w)}([^a-z]|$)", t) for w in BANNED_WORDS)


def matches(c: dict, shot: dict) -> bool:
    if banned(c):
        return False
    t = _text(c)
    return all(any(w in t for w in grp) for grp in shot["must"])


def _pool(a: Adapter, offline: bool, snap: dict, cache: dict) -> dict:
    """query -> candidates for one adapter over every query in SHOTS (searched once, cached)."""
    if a.name not in cache:
        if offline:
            cache[a.name] = (snap.get("by_source") or {}).get(a.name) or {}
        else:
            cache[a.name] = {q: a.search(q) for q in sorted({s["query"] for s in SHOTS})}
    return cache[a.name]


def resolve(shots: list[dict] | None = None, offline: bool = False,
            recorded: dict | None = None) -> dict:
    """One clip per need, falling through the chain. offline: read the recorded
    candidates instead of searching (the CI form of the same proof)."""
    shots = shots or SHOTS
    snap = recorded if recorded is not None else (
        json.loads(CANDIDATES.read_text()) if offline and CANDIDATES.exists() else {})
    used: set[str] = set()
    picks, misses, tried = [], [], {}
    cache: dict = {}
    for shot in shots:
        got = None
        for a in CHAIN:
            ok, why = a.enabled()
            tried.setdefault(a.name, why)
            if not ok:
                continue
            try:
                pool = _pool(a, offline, snap, cache)
            except Exception as e:                           # noqa: BLE001
                tried[a.name] = f"search failed: {str(e)[:80]}"
                continue
            cands = list(pool.get(shot["query"]) or [])
            # a reviewed pick may have surfaced under another need's query
            want = set(PREFER.get(shot["need"]) or [])
            cands += [c for q, cs in pool.items() if q != shot["query"] for c in cs
                      if f"{a.name}:{c['id']}" in want]
            pref = PREFER.get(shot["need"]) or []
            cands = sorted(cands, key=lambda c: (pref.index(f"{a.name}:{c['id']}")
                                                 if f"{a.name}:{c['id']}" in pref else len(pref)))
            for c in cands:
                uid = f"{a.name}:{c['id']}"
                c = {**c, "source": a.name}
                if uid in used or uid in REFUSED or banned(c):
                    continue
                if uid not in pref and not strict(c, shot):
                    continue
                got = {**c, "source": a.name, "licence": c.get("licence") or a.licence,
                       "need": shot["need"], "uid": uid}
                break
            if got:
                break
        if got:
            used.add(got["uid"])
            picks.append(got)
        else:
            misses.append(shot["need"])
    by_src: dict[str, int] = {}
    for p in picks:
        by_src[p["source"]] = by_src.get(p["source"], 0) + 1
    return {"picks": picks, "misses": misses, "count": len(picks), "by_source": by_src,
            "adapters": tried, "enough": len(picks) >= MIN_REAL_CLIPS}


def snapshot() -> dict:
    """Search every enabled adapter for every need's query; record the candidates."""
    out: dict = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "queries": sorted({s["query"] for s in SHOTS}), "adapters": sources_status(),
                 "by_source": {}}
    for a in CHAIN:
        if not a.enabled()[0]:
            continue
        out["by_source"][a.name] = {}
        for q in out["queries"]:
            try:
                out["by_source"][a.name][q] = [
                    {k: c.get(k) for k in ("id", "title", "item_url", "duration", "width",
                                           "licence", "author")} for c in a.search(q)]
            except Exception as e:                           # noqa: BLE001
                out["by_source"][a.name][q] = []
                out.setdefault("errors", []).append(f"{a.name} {q!r}: {str(e)[:100]}")
    CANDIDATES.write_text(json.dumps(out, indent=1) + "\n")
    return out


# ---------------------------------------------------------------- harvest
def _record(pick: dict, shot: dict, meta: dict, blob: bytes) -> dict:
    a = BY_NAME[pick["source"]]
    stem = re.sub(r"[^a-z0-9]+", "-", str(pick.get("title") or pick["id"]).lower()).strip("-")[:48]
    ext = os.path.splitext(urllib.parse.urlparse(meta["download_url"]).path)[1].lower() or ".mp4"
    fname = f"food_clip__{shot['need']}__{pick['source']}-{re.sub(r'[^A-Za-z0-9]+', '-', pick['id'])[:40]}__{stem}{ext}"
    CLIPS.mkdir(parents=True, exist_ok=True)
    (CLIPS / fname).write_bytes(blob)
    lic = meta.get("licence") or pick.get("licence") or a.licence
    if pick["source"] in ("commons", "archive"):
        lic = "Public domain" if "public" in lic.lower() or "mark" in lic.lower() else lic
    who = a.credit or meta.get("source_org") or pick["source"]
    return {
        "subject": shot["need"], "key": shot["need"], "label": shot["label"],
        "source": pick["source"], "source_id": pick["id"], "title": pick.get("title"),
        "item_url": pick.get("item_url"), "download_url": meta["download_url"],
        "licence": lic, "licence_url": a.licence_url, "licence_text": a.licence_text,
        "terms_url": a.terms_url, "terms_text": a.terms_text,
        "licence_basis": meta["licence_basis"], "attribution_required": False,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sha256": hashlib.sha256(blob).hexdigest(), "local_file": f"clips/{fname}",
        # Credited on screen even where the licence does not require it.
        "credit_line": f"{shot['label']} - FOOTAGE, {who[:36].upper()} ({lic.upper()[:40]})",
        "source_org": meta.get("source_org") or who, "depicts": "video",
        "subject_basis": shot["basis"], "uses": shot["uses"], "sound": shot.get("sound"),
        "segment": shot.get("segment", "chocolate"),
        "ai_generated": False, **probe(CLIPS / fname),
        **shot_extras(shot, f"{pick['source']}:{pick['id']}"),
    }


def shot_extras(shot: dict, uid: str) -> dict:
    """Per-clip review fields carried from the shot list onto its record: the
    usable ranges and crop (the VOA report, a clip whose opening shows hands),
    the segment, and the reviewed hands answer (HANDS)."""
    out = {"segment": shot.get("segment", "chocolate"), "sound": shot.get("sound")}
    for k in ("ranges", "crop"):
        v = (shot.get(k) or {}).get(uid)
        if v:
            out[k] = v
    h = HANDS.get(shot["need"])
    if h is not None:
        out["hands"], out["hands_basis"] = bool(h[0]), h[1]
    return out


# RICHNESS (owner, 13 Oct 2026: "favour the richest-looking clips - gloss,
# depth, saturation - score candidates for it and record the score"). Measured
# on five frames of the clip itself, numpy only: saturation (HSV S), contrast
# (luma spread), gloss (share of near-white specular pixels inside saturated
# regions) and detail (mean luma gradient). visuals/food.pool_for ranks by it
# after fit and hands.
RICHNESS_WEIGHTS = {"saturation": 0.35, "contrast": 0.25, "gloss": 0.15, "detail": 0.25}


def richness(path: Path, ranges: list | None = None, n: int = 5) -> dict:
    import numpy as np                                         # noqa: PLC0415
    dur = float(probe(path).get("duration_s") or 0) or 10.0
    lo, hi = (ranges[0] if ranges else (0.0, dur))
    sat = con = glo = det = 0.0
    got = 0
    for k in range(n):
        t = lo + (hi - lo) * (k + 0.5) / n
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(path),
                              "-frames:v", "1", "-vf", "scale=192:108", "-f", "rawvideo",
                              "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
        if len(raw) != 192 * 108 * 3:
            continue
        a = np.frombuffer(raw, np.uint8).reshape(108, 192, 3).astype(np.float32) / 255
        mx, mn = a.max(-1), a.min(-1)
        s = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
        lum = a @ np.array([0.299, 0.587, 0.114], np.float32)
        sat += float(s.mean())
        con += float(min(1.0, lum.std() / 0.25))
        spec = (lum > 0.85) & (np.roll(s, 2, 0) > 0.35)
        glo += float(min(1.0, spec.mean() * 20))
        det += float(min(1.0, (np.abs(np.diff(lum, axis=0)).mean() + np.abs(np.diff(lum, axis=1)).mean()) * 12))
        got += 1
    if not got:
        return {"score": 0.0, "frames": 0}
    parts = {"saturation": sat / got, "contrast": con / got, "gloss": glo / got, "detail": det / got}
    score = sum(RICHNESS_WEIGHTS[k] * min(1.0, v) for k, v in parts.items())
    return {"score": round(score, 3), **{k: round(v, 3) for k, v in parts.items()}, "frames": got}


def black_spans(path: Path) -> list[list[float]]:
    """Spans of (near) black picture, by ffmpeg blackdetect. A stock clip that
    opens on 2.9 s of black (pixabay:71743) put a black frame in the first
    full render's cold open; visuals/food_motion._span never uses them."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-vf",
                        "blackdetect=d=0.2:pix_th=0.12", "-an", "-f", "null", "-"],
                       capture_output=True, text=True)
    out = []
    for m in re.finditer(r"black_start:([\d.]+) black_end:([\d.]+)", r.stderr):
        out.append([round(float(m.group(1)), 3), round(float(m.group(2)), 3)])
    return out


def score_richness(index: list[dict]) -> list[dict]:
    for r in index:
        path = IMAGERY / r["local_file"]
        if path.exists() and (r.get("richness") or {}).get("sha256") != r.get("sha256"):
            r["richness"] = {**richness(path, r.get("ranges")), "sha256": r.get("sha256")}
        if path.exists() and (r.get("black") or {}).get("sha256") != r.get("sha256"):
            r["black"] = {"spans": black_spans(path), "sha256": r.get("sha256")}
    return index


def load() -> dict:
    return json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"index": []}


def save(index: list[dict], rejected: list[dict], resolved: dict | None = None) -> dict:
    man = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "domain": "food-science",
        "module": "research/food_footage.py",
        "policy": ("Real video only, through the free fallback chain (Pixabay, Pexels, Mixkit, "
                   "[Coverr disabled by its terms], Commons PD/CC0, Internet Archive PD collections, "
                   "NASA). Licences allow commercial reuse without attribution; every clip is "
                   "still credited on screen."),
        "rights_fields_required": RIGHTS_FIELDS,
        "asset_count": sum(1 for r in index if not r.get("excluded")),
        "chain": [a.name for a in CHAIN],
        "sources": sources_status(),
        "resolved_by_source": (resolved or {}).get("by_source"),
        "rejected": rejected,
        "index": sorted(index, key=lambda r: r["subject"]),
    }
    MANIFEST.write_text(json.dumps(man, indent=2) + "\n")
    return man


def harvest(only_missing: bool = True) -> dict:
    prior = {r["subject"]: r for r in load().get("index") or [] if r.get("source") in BY_NAME}
    res = resolve()
    # The manifest is exactly what resolves now: a need whose pick changed, or
    # that no longer resolves, never keeps its old clip.
    index, rejected, fetched = {}, [], 0
    shot_by = {s["need"]: s for s in SHOTS}
    for pick in res["picks"]:
        shot = shot_by[pick["need"]]
        old = prior.get(shot["need"])
        if only_missing and old and old.get("source_id") == pick["id"] \
                and (IMAGERY / old["local_file"]).exists():
            index[shot["need"]] = {**old, **shot_extras(shot, f"{pick['source']}:{pick['id']}")}
            continue
        if fetched >= MAX_PER_RUN:
            rejected.append({"subject": shot["need"], "reason": f"per-run cap {MAX_PER_RUN}"})
            continue
        try:
            meta, blob = BY_NAME[pick["source"]].download(pick)
        except Exception as e:                                # noqa: BLE001
            rejected.append({"subject": shot["need"], "source": pick["source"], "reason": str(e)[:200]})
            continue
        index[shot["need"]] = _record(pick, shot, meta, blob)
        fetched += 1
        print(f"  CLIP {shot['need']:<16} {pick['source']:<8} {index[shot['need']]['duration_s']:6.1f}s")
        save(list(index.values()), rejected, res)
    for need in res["misses"]:
        rejected.append({"subject": need, "reason": "no adapter in the chain had a matching clip"})
    return save(score_richness(list(index.values())), rejected, res)


def record_problems(rec: dict) -> list[str]:
    """Rights fields on one record - no bytes needed (CI has no clips)."""
    s = rec.get("subject")
    p = [f"{s}: missing {k}" for k in RIGHTS_FIELDS if not rec.get(k)]
    a = BY_NAME.get(rec.get("source") or "")
    if not a:
        return p + [f"{s}: source {rec.get('source')!r} is not in the chain"]
    if a.terms_block:
        p.append(f"{s}: from {a.name}, whose terms forbid automated access")
    if a.name in ("commons", "archive", "nasa"):
        if not re.search(r"public domain|cc0", rec.get("licence") or "", re.I):
            p.append(f"{s}: {a.name} clip licence {rec.get('licence')!r} is not PD/CC0")
    elif rec.get("licence") != a.licence:
        p.append(f"{s}: licence {rec.get('licence')!r} is not {a.name}'s ({a.licence})")
    if a.licence_text and rec.get("licence_text") != a.licence_text:
        p.append(f"{s}: licence wording not recorded")
    if rec.get("ai_generated"):
        p.append(f"{s}: an AI clip in the real-footage manifest")
    return p


def verify(check_bytes: bool = True) -> int:
    n = 0
    for rec in load().get("index") or []:
        if rec.get("excluded"):
            continue
        probs = record_problems(rec)
        if probs:
            raise AssertionError("; ".join(probs))
        for k in ("licence_text", "terms_text"):
            if rec.get(k) and not (IMAGERY / rec[k]).exists():
                raise AssertionError(f"{rec['subject']}: {rec[k]} is not committed")
        if check_bytes:
            path = IMAGERY / rec["local_file"]
            if not path.exists():
                raise AssertionError(f"{rec['subject']}: {rec['local_file']} is not on disk")
            if hashlib.sha256(path.read_bytes()).hexdigest() != rec["sha256"]:
                raise AssertionError(f"{rec['subject']}: sha256 changed since it was fetched")
        n += 1
    if n == 0:
        raise AssertionError("verified zero clips - an empty index must fail, not pass")
    return n


def main(argv: list[str]) -> int:
    if "--verify" in argv:
        print(f"food footage verified: {verify()} clips, sha256 matched")
        return 0
    if "--sources" in argv:
        print(json.dumps(sources_status(), indent=1))
        return 0
    if "--snapshot" in argv:
        s = snapshot()
        n = {a: sum(len(v) for v in qs.values()) for a, qs in s["by_source"].items()}
        print(json.dumps({"candidates": n, "errors": s.get("errors", [])}, indent=1))
        return 0 if any(n.values()) else 1
    if "--resolve" in argv:
        r = resolve(offline="--offline" in argv)
        for p in r["picks"]:
            print(f"  {p['need']:<16} {p['source']:<8} {p['id'][:40]:<40} {str(p.get('title'))[:50]}")
        print(json.dumps({k: r[k] for k in ("count", "by_source", "misses", "adapters")}, indent=1))
        if not r["enough"]:
            print(f"FAIL: {r['count']} real clips resolved, fewer than {MIN_REAL_CLIPS}")
            return 1
        print(f"ok: {r['count']} real clips resolved (>= {MIN_REAL_CLIPS})")
        return 0
    if "--harvest" in argv:
        m = harvest()
        print(f"{m['asset_count']} clips -> {MANIFEST.relative_to(ROOT)}; {len(m['rejected'])} not fetched")
        for r in m["rejected"]:
            print("  not fetched:", r)
        return 0 if m["asset_count"] >= MIN_REAL_CLIPS else 1
    print(__doc__.split("\n\n")[0])
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
