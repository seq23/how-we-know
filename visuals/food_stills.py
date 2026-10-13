"""AI stills for the food preset, on Workers AI's free daily allowance. $0.

The owner's brief (2026-10-13): marvellous, hypnotic, realistic not animated,
AI is fine, FANTASTICAL IN SCALE NOT PHYSICS - fields of dough rising, a
thousand steaks, chocolate falling in sheets. Real things that are real get
real pictures (research/imagery_food.py); this module makes only the
impossible-scale and explanatory shots no camera can take.

ROUTE. `@cf/black-forest-labs/flux-1-schnell` on Cloudflare Workers AI, called
with the wrangler login already on this Mac (its OAuth token carries
`ai (write)`; read from wrangler's own config, never printed). Workers AI gives
every account 10,000 neurons a day free; a 1024x576 schnell image at 4 steps
is about 60 neurons. DAILY_CAP below keeps a day's generation under a third of
the free allowance, so this can never be what tips the account into paid use,
and the manifest is the ledger that enforces it (count per UTC day).

LOCAL SD. diffusers is installed in the TTS venv but no Stable Diffusion
weights are on this Mac and the machine has 8 GB of unified memory; Workers AI
is the faster $0 path. No open video model runs on this Mac either, so there
are NO AI video clips: every AI shot is a still given motion by visuals/food.py.

PROVENANCE. Every image is recorded in channel/imagery/food_ai.json with its
prompt, seed, model, sha256, `ai_generated: true` and
`altered_content: true` - realistic AI imagery must carry YouTube's
altered-or-synthetic-content disclosure, and the episode spec reads that flag
from here (visuals/food.py episode_spec).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "channel" / "imagery"
ASSETS = OUT / "assets"
MANIFEST = OUT / "food_ai.json"
ACCOUNT = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "8d147e242033699dd37c6f5a451f48d2")
MODEL = "@cf/black-forest-labs/flux-1-schnell"
STEPS = 4                      # schnell's own default; quality is flat above it
NEURONS_PER_IMAGE = 60         # conservative: ~58 at 1024x576, 4 steps
FREE_NEURONS_PER_DAY = 10_000
DAILY_CAP = 50                 # 50 x 60 = 3,000 neurons, under a third of free

# The preset's look, appended to every prompt so a set reads as one film:
# dark warm ground, one glossy subject, side light, macro realism.
LOOK = ("photorealistic macro food photography, single glossy subject lit from "
        "the side by one warm key light, deep dark warm background, rich "
        "saturated colour, shallow depth of field, cinematic, no text, no "
        "people, no hands, no logos")


def _token() -> str:
    """Wrangler's OAuth token, read in-process and never echoed."""
    tok = os.environ.get("CLOUDFLARE_API_TOKEN")
    if tok:
        return tok
    # Wrangler 4 keeps its login in ~/.wrangler; older installs used
    # ~/Library/Preferences/.wrangler. Newest expiry wins (an expired token
    # 401s as "Authentication error"; `npx wrangler whoami` refreshes it).
    best = None
    for cfg in (Path.home() / ".wrangler/config/default.toml",
                Path.home() / "Library/Preferences/.wrangler/config/default.toml"):
        if not cfg.exists():
            continue
        txt = cfg.read_text()
        tok = re.search(r'^oauth_token\s*=\s*"([^"]+)"', txt, re.M)
        exp = re.search(r'^expiration_time\s*=\s*"([^"]+)"', txt, re.M)
        if tok and (best is None or (exp and exp.group(1) > best[1])):
            best = (tok.group(1), exp.group(1) if exp else "")
    m = best
    if m:
        return m[0]
    if not m:
        raise SystemExit("NAMED STOP [AI_STILLS_NO_TOKEN]: no wrangler login on "
                         "this Mac; run `npx wrangler login` once")
    raise AssertionError("unreachable")


def load() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return {"_why": __doc__.split("\n\n")[0], "model": MODEL,
            "free_neurons_per_day": FREE_NEURONS_PER_DAY,
            "neurons_per_image_estimate": NEURONS_PER_IMAGE,
            "daily_cap": DAILY_CAP, "index": []}


def used_today(man: dict, day: str | None = None) -> int:
    day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return sum(1 for r in man["index"] if (r.get("generated_at") or "")[:10] == day)


def generate(key: str, prompt: str, seed: int = 7, width: int = 1024,
             height: int = 576) -> dict:
    """One still, recorded. Refuses past the daily cap, never spends past free."""
    man = load()
    prior = next((r for r in man["index"] if r["key"] == key
                  and r["prompt"] == prompt and r["seed"] == seed), None)
    if prior and (OUT / prior["local_file"]).exists():
        return prior
    if used_today(man) >= DAILY_CAP:
        raise SystemExit(f"NAMED STOP [AI_STILLS_DAILY_CAP]: {DAILY_CAP} stills "
                         f"made today - the cap that keeps Workers AI inside its "
                         f"free allowance. Resumes tomorrow (UTC).")
    full = f"{prompt}. {LOOK}"
    # schnell takes prompt, steps and seed only and returns 1024x1024; the
    # preset crops 16:9 from it (visuals/food.py), so width/height are
    # recorded as the crop the shot is planned for, not sent.
    # The endpoint takes no seed either ('/seed' not allowed, 2026-10-13), so
    # `seed` is a VARIANT number in the key and file name; the sha256 is the
    # record of exactly which picture was made.
    body = json.dumps({"prompt": full, "steps": STEPS}).encode()
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/ai/run/{MODEL}",
        data=body, method="POST",
        headers={"Authorization": f"Bearer {_token()}",
                 "Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                res = json.loads(r.read())
            break
        except Exception as e:                                # noqa: BLE001
            detail = getattr(e, "read", lambda: b"")()[:300]
            if attempt == 2 or getattr(e, "code", None) in (400, 401, 403):
                raise SystemExit(f"NAMED STOP [AI_STILLS_FAILED]: {key}: {e} {detail!r}")
            time.sleep(4 * (attempt + 1))
    img = base64.b64decode(res["result"]["image"])
    ASSETS.mkdir(parents=True, exist_ok=True)
    fname = f"food_ai__{key}__s{seed}.jpg"
    (ASSETS / fname).write_bytes(img)
    rec = {"key": key, "prompt": prompt, "full_prompt": full, "seed": seed,
           "model": MODEL, "steps": STEPS, "width": width, "height": height,
           "local_file": f"assets/{fname}",
           "sha256": hashlib.sha256(img).hexdigest(),
           "generated_at": datetime.now(timezone.utc).isoformat(),
           "ai_generated": True, "altered_content": True,
           "licence": "generated on Workers AI (FLUX.1 [schnell], Apache-2.0 "
                      "weights); output owned by the channel",
           "credit_line": "AI-GENERATED IMAGE"}
    man["index"] = [r for r in man["index"] if not (r["key"] == key and r["seed"] == seed)]
    man["index"].append(rec)
    MANIFEST.write_text(json.dumps(man, indent=2) + "\n")
    return rec


if __name__ == "__main__":
    k, p = sys.argv[1], sys.argv[2]
    print(json.dumps(generate(k, p), indent=1)[:400])
