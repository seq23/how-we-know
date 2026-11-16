#!/usr/bin/env python3
"""Whisper Almanac's channel face: avatar, banner, About text and keywords.

    .venv/bin/python loop/whisper_branding.py build    # avatar + banner PNGs, no network
    .venv/bin/python loop/whisper_branding.py apply    # banner, About, keywords to @whisperalmanac

The approved brand (6 Nov 2026, ~/Brains/spry.md Voice > Whisper Almanac;
config/whisper_almanac.json `brand`): one candle in a dark room, dark only,
the wordmark in DM Serif Display italic lowercase with a small ember flame over
the end, the avatar the flame in a dark circle. Drawn here in Pillow, $0.

  * avatar.png  800x800. YouTube's API cannot set a profile picture: it is
    uploaded once by hand in YouTube Studio (Customisation > Branding).
  * banner.png  2560x1440; every word and the flame sit inside the 1546x423
    safe area every device shows (check_banner proves it from the pixels).
  * apply: channelBanners.insert (50 units) + ONE channels.update
    part=brandingSettings (50 units) carrying the banner URL, the About text
    and keywords (config `about`), merged onto the live object so nothing else
    on it is reset, then read back. Re-running changes nothing that matches.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

LOOP = Path(__file__).resolve().parent
ROOT = LOOP.parent
sys.path.insert(0, str(LOOP))

import whisper_lane as WL                                   # noqa: E402

OUT = ROOT / "channel" / "whisper" / "branding"
AVATAR, BANNER = OUT / "avatar.png", OUT / "banner.png"
BW, BH = 2560, 1440
SAFE = ((BW - 1546) // 2, (BH - 423) // 2, (BW + 1546) // 2, (BH + 423) // 2)
API = "https://www.googleapis.com/youtube/v3"
UPLOAD_API = "https://www.googleapis.com/upload/youtube/v3"


def _hex(h: str) -> tuple[int, int, int]:
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def flame(h: int, b: dict):
    """A teardrop candle flame h pixels tall, with its own soft glow (RGBA)."""
    from PIL import Image, ImageDraw, ImageFilter          # noqa: PLC0415
    w = int(h * 0.5)
    pad = h
    img = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    glow = Image.new("RGBA", img.size, _hex(b["ember"]) + (0,))
    ImageDraw.Draw(glow).ellipse((pad - w * 0.9, pad + h * 0.05, pad + w * 1.9, pad + h * 1.05),
                                 fill=_hex(b["ember"]) + (110,))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(h * 0.35)))

    def drop(scale: float, colour: tuple, dy: float = 0.0):
        """A teardrop: the tip at the top, the round belly at the bottom."""
        import math                                         # noqa: PLC0415
        hh, r = h * scale, w * scale * 0.62
        cx, bottom = pad + w / 2, pad + h + dy
        tip = bottom - hh
        pts = [(cx + r * math.sin(t) * math.sin(t / 2) ** 1.3, tip + hh * (1 - math.cos(t)) / 2)
               for t in (2 * math.pi * i / 360 for i in range(360))]
        layer = Image.new("RGBA", img.size, colour[:3] + (0,))   # no dark fringe when blurred
        ImageDraw.Draw(layer).polygon(pts, fill=colour)
        return layer.filter(ImageFilter.GaussianBlur(max(1, h * 0.004)))

    img = Image.alpha_composite(img, drop(1.0, _hex(b["ember"]) + (255,)))
    img = Image.alpha_composite(img, drop(0.55, (251, 227, 176, 255), dy=-h * 0.04))
    return img, (pad, pad, pad + w, pad + h)


def _glow_ground(size: tuple[int, int], centre: tuple[int, int], r: int, b: dict):
    from PIL import Image, ImageDraw, ImageFilter          # noqa: PLC0415
    img = Image.new("RGB", size, b["ground"])
    g = Image.new("RGB", size, b["ground"])
    d = ImageDraw.Draw(g)
    cx, cy = centre
    for k, col in ((1.0, b["glow"]), (0.55, "#4A2F1A")):
        d.ellipse((cx - r * k, cy - r * k, cx + r * k, cy + r * k), fill=col)
    return Image.blend(img, g.filter(ImageFilter.GaussianBlur(r * 0.45)), 0.85)


def build_avatar(b: dict, out: Path = AVATAR) -> Path:
    """800x800: the flame in a dark circle (YouTube crops the avatar round)."""
    from PIL import Image, ImageDraw                       # noqa: PLC0415
    img = _glow_ground((800, 800), (400, 430), 330, b)
    ImageDraw.Draw(img).ellipse((40, 40, 760, 760), outline=_hex(b["glow"]), width=6)
    f, (x0, y0, x1, y1) = flame(400, b)
    img = img.convert("RGBA")
    img.alpha_composite(f, (400 - (x0 + x1) // 2, 400 - (y0 + y1) // 2 - 10))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out, "PNG", optimize=True)
    return out


def _fit(d, text: str, name: str, size: int, maxw: int):
    font = WL._font(name, size)
    while d.textlength(text, font=font) > maxw and size > 20:
        size -= 2
        font = WL._font(name, size)
    return font


def build_banner(b: dict, about: dict, out: Path = BANNER) -> Path:
    """2560x1440: the wordmark with its flame over the end, then what the
    channel is ("Nightly ASMR for sleep", her ask 16 Nov 2026), then what is
    in it, all inside the safe area and big enough to read on a phone (the
    safe area shows at about a quarter size there)."""
    from PIL import Image, ImageDraw                       # noqa: PLC0415
    img = _glow_ground((BW, BH), (BW // 2, BH // 2), 620, b).convert("RGBA")
    d = ImageDraw.Draw(img)
    word = "whisper almanac"
    size = 130
    font = WL._font("DMSerifDisplay-Italic.ttf", size)
    tw = d.textlength(word, font=font)
    x = (BW - tw) / 2
    base_y = SAFE[1] + 178
    d.text((x, base_y), word, font=font, fill=b["ink"], anchor="ls")
    # the flame over the end: above the final letter, as the logo is drawn
    last = d.textlength(word[:-1], font=font)
    cw = d.textlength(word[-1], font=font)
    f, (x0, y0, x1, y1) = flame(84, b)
    fx = int(x + last + cw * 0.55 - (x0 + x1) / 2)
    fy = int(base_y - size * 0.62 - (y1 - y0) - y0 - 6)
    img.alpha_composite(f, (fx, fy))
    d = ImageDraw.Draw(img)
    maxw = SAFE[2] - SAFE[0] - 40
    big = _fit(d, about["banner_line"], "Jost.ttf", 100, maxw)
    d.text((BW / 2, base_y + 44), about["banner_line"], font=big, fill=b["ink"], anchor="ma")
    sub = _fit(d, about["banner_sub"], "Jost-Light.ttf", 58, maxw)
    d.text((BW / 2, base_y + 44 + big.size + 22), about["banner_sub"], font=sub, fill="#CDBFA6", anchor="ma")
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out, "PNG", optimize=True)
    return out


def check_banner(path: Path, b: dict) -> list[str]:
    """Everything brighter than the glow sits inside the safe area; dark only."""
    from PIL import Image, ImageStat                       # noqa: PLC0415
    im = Image.open(path).convert("L")
    bad = []
    if im.size != (BW, BH):
        bad.append(f"banner is {im.size}, not {(BW, BH)}")
    mask = im.point(lambda v: 255 if v > 110 else 0)
    box = mask.getbbox()
    if not box:
        bad.append("no wordmark found on the banner")
    elif not (box[0] >= SAFE[0] and box[1] >= SAFE[1] and box[2] <= SAFE[2] and box[3] <= SAFE[3]):
        bad.append(f"bright pixels at {box} fall outside the safe area {SAFE}")
    if ImageStat.Stat(im).mean[0] > 60:
        bad.append("the banner is not dark")
    return bad


def build() -> tuple[Path, Path]:
    c = WL.cfg()
    a = build_avatar(c["brand"])
    bn = build_banner(c["brand"], c["about"])
    probs = check_banner(bn, c["brand"])
    if probs:
        raise SystemExit("FAIL: " + "; ".join(probs))
    return a, bn


def _call(token: str, method: str, url: str, data: bytes | None = None, ctype: str = "application/json"):
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read() or b"{}")


def apply() -> int:
    import quota                                            # noqa: PLC0415
    import whisper_upload as WU                             # noqa: PLC0415
    c = WL.cfg()
    _, banner = build()
    creds = WU.credentials(c)
    if creds is None:
        print("NAMED STOP WHISPER_YT_TOKEN_INVALID: no usable @whisperalmanac token")
        return 3
    tok = WU.YouTube(creds).token
    ch = _call(tok, "GET", f"{API}/channels?part=brandingSettings&mine=true")["items"][0]
    if ch["id"] != c["channel"]["id"]:
        print(f"NAMED STOP WHISPER_WRONG_CHANNEL: token is for {ch['id']}")
        return 3
    if not WU.afford_units(100, quota.deferrable_reserve):
        print(f"NAMED STOP UPLOAD_QUOTA: no room for 100 units today. {WU.quota_line()}")
        return 3
    url = _call(tok, "POST", f"{UPLOAD_API}/channelBanners/insert?uploadType=media",
                banner.read_bytes(), "image/png")["url"]
    bs = ch["brandingSettings"]
    bs.setdefault("channel", {}).update({"description": c["about"]["description"],
                                         "keywords": c["about"]["keywords"]})
    bs.setdefault("image", {})["bannerExternalUrl"] = url
    _call(tok, "PUT", f"{API}/channels?part=brandingSettings",
          json.dumps({"id": ch["id"], "brandingSettings": bs}).encode())
    WU.book(100, "whisper-branding")
    got = _call(tok, "GET", f"{API}/channels?part=brandingSettings&mine=true")["items"][0]["brandingSettings"]
    ok = (got["channel"].get("description", "").strip() == c["about"]["description"].strip()
          and (got.get("image") or {}).get("bannerExternalUrl"))
    print(f"OUTPUT banner {'set' if (got.get('image') or {}).get('bannerExternalUrl') else 'MISSING'}, "
          f"About {'matches' if ok else 'DOES NOT match'}, keywords {got['channel'].get('keywords', '')[:60]!r}")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    if argv[:1] == ["build"]:
        a, b = build()
        print(f"OUTPUT avatar {a}\nOUTPUT banner {b}")
        return 0
    if argv[:1] == ["apply"]:
        return apply()
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
