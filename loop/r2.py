"""Cloudflare R2 — the shelf the cloud upload lane takes its renders off.

WHY THIS EXISTS. Uploading to YouTube used to require the owner's Mac to be
awake at 09:00, because that is where `renders/*-final.mp4` lives and renders
are gitignored (too large for history, regenerable in ten minutes). GitHub
Actions has the credentials and the schedule but not the bytes. R2 is the
bridge: the Mac pushes finished renders and thumbnails up once, and the cloud
lane pulls whichever episode it is about to publish.

    bucket   how-we-know-renders
    keys     renders/<slug>-final.mp4        thumbnails/<slug>.jpg

TWO VARIABLES, AND BOTH ARE NAMED WHEN ABSENT:

    CLOUDFLARE_ACCOUNT_ID    8d147e…  — not a secret; a plain workflow `env`
    CLOUDFLARE_API_TOKEN     the owner's Cloudflare API token — a repo secret

`require()` raises `R2Unavailable` carrying the exact variable names that are
missing. Never a crash and never a silent skip: "the cloud lane ran and
uploaded nothing" is indistinguishable from success from the outside, which is
the failure class this repo keeps paying for.

──────────────────────────────────────────────────────────────────────────────
THE TRAP. READ THIS BEFORE DEBUGGING ANY `wrangler r2` FAILURE.

Without `CLOUDFLARE_ACCOUNT_ID` set, wrangler resolves the account by calling
`/memberships`. An R2-scoped API token cannot read that endpoint, so EVERY r2
command fails with:

    Authentication error [code: 10000]

which looks exactly like a missing R2 permission on the token, and sends you to
re-issue a token that was never the problem. Setting `CLOUDFLARE_ACCOUNT_ID`
explicitly skips the membership lookup and everything works. This module always
passes it through to the subprocess for that reason, and `_run()` re-labels a
code-10000 failure with this explanation rather than letting it read as a
permissions problem.
──────────────────────────────────────────────────────────────────────────────

WHY WRANGLER AND NOT boto3. R2 does speak S3, but that needs a *second*
credential — an R2 S3 API token with its own access key and secret, four more
variables to create, store and rotate. The owner already has a working
Cloudflare API token and wrangler already authenticates with it. One credential
that exists beats four that have to be minted.

WHAT WRANGLER CANNOT DO. `wrangler r2 object` has exactly get, put and delete —
there is no HEAD and no LIST. So every object is pushed with a tiny sidecar,
`<key>.meta.json`, holding its size and sha256. `head()` fetches the sidecar,
which is a few hundred bytes, and that is what makes existence checks and
change detection cheap. The sidecar is written AFTER the object, so a sidecar
present always means the bytes landed; the reverse would let a half-finished
push look complete.

VERIFICATION IS SIZE **AND** CHECKSUM, never the key name: a render re-cut
under the same slug keeps its name, and pushing by name alone would leave the
old cut on the shelf forever.

THE LOCAL STUB. `R2_LOCAL_DIR=/some/path` runs every operation against that
directory instead of the network, same key layout, same sidecars, same
verification. That is not a convenience — it is how the whole upload lane is
exercised in tests that have no credentials and must never touch the real
bucket or the real channel. The stub WINS over credentials when both are set,
so a test cannot reach production by accident.

DRY RUN. `LOOP_DRY_RUN=1` refuses to build the credentialled backend at all and
refuses every write on either backend.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_BUCKET = "how-we-know-renders"
REQUIRED_VARS = ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN")

RENDER_PREFIX = "renders/"
THUMB_PREFIX = "thumbnails/"
SHORT_PREFIX = "shorts/"
META_SUFFIX = ".meta.json"

# Pin the major. wrangler 4 is what the r2 object contract above was verified
# against; a 5.x that changes the flags must be adopted deliberately.
WRANGLER_NPX = ["npx", "--yes", "wrangler@4"]

# The wrangler login on the owner's Mac. When this exists, wrangler already has
# a credential and CLOUDFLARE_API_TOKEN is not additionally required — which is
# why the token is only reported missing on a machine with no login, i.e. CI.
#
# Two locations, because wrangler picks by platform and the macOS one is not the
# documented default: on macOS the login lands under Library/Preferences, and
# checking only the XDG path made a logged-in Mac report the token missing.
WRANGLER_LOGINS = (
    Path.home() / "Library" / "Preferences" / ".wrangler" / "config" / "default.toml",
    Path.home() / ".config" / ".wrangler" / "config" / "default.toml",
    Path.home() / ".wrangler" / "config" / "default.toml",
)


def dry_run() -> bool:
    """Read at call time, not at import: tests set it around a single call."""
    return os.environ.get("LOOP_DRY_RUN") == "1"


class R2Unavailable(Exception):
    """R2 cannot be used, and this is the named reason.

    Carries `code`, `message` and `unblock` in the exact shape
    `Stage.named_stop` wants, so no caller has to invent wording.
    """

    def __init__(self, code: str, message: str, unblock: str = "",
                 detail=None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.unblock = unblock
        self.detail = detail


def bucket_name(env=None) -> str:
    e = os.environ if env is None else env
    return (e.get("R2_BUCKET") or "").strip() or DEFAULT_BUCKET


def render_key(slug: str) -> str:
    return f"{RENDER_PREFIX}{slug}-final.mp4"


def thumb_key(slug: str) -> str:
    return f"{THUMB_PREFIX}{slug}.jpg"


def short_key(slug: str, rank: int = 1) -> str:
    """The shelf key of one cut: rank 1 is `<slug>-short.mp4`, rank N is
    `<slug>-shortN.mp4`, the names visuals/shorts.py writes. Ranks 2 and 3 are
    shelved only for the domains `shorts_lane.cuts_for` allows (deep sea,
    owner build 2026-10-08)."""
    name = f"{slug}-short.mp4" if rank == 1 else f"{slug}-short{rank}.mp4"
    return f"{SHORT_PREFIX}{name}"


def short_receipt_key(slug: str, rank: int = 1) -> str:
    """The `.short.json` beside the cut — what V14/V15 read to do their work.

    It is shelved with the Short so the evidence travels with the artefact.
    Without it nobody downstream can re-check which beats were used or where
    the caption band was cropped.
    """
    return f"{short_key(slug, rank)}.short.json"


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def content_type(path) -> str:
    s = Path(path).suffix.lower()
    return {".mp4": "video/mp4", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".json": "application/json"}.get(s, "application/octet-stream")


# --------------------------------------------------------------- credentials

def has_wrangler_login() -> bool:
    return any(p.exists() for p in WRANGLER_LOGINS)


def missing_vars(env=None) -> list[str]:
    """Exactly which required variables are absent, for this machine.

    CLOUDFLARE_ACCOUNT_ID is always required — see THE TRAP above; it is the
    difference between working and an authentication error that lies about its
    cause. CLOUDFLARE_API_TOKEN is required only where wrangler has no
    interactive login of its own, which is every CI runner.
    """
    e = os.environ if env is None else env
    gone = []
    if not (e.get("CLOUDFLARE_ACCOUNT_ID") or "").strip():
        gone.append("CLOUDFLARE_ACCOUNT_ID")
    if not (e.get("CLOUDFLARE_API_TOKEN") or "").strip() \
            and not has_wrangler_login():
        gone.append("CLOUDFLARE_API_TOKEN")
    return gone


def local_dir(env=None) -> Path | None:
    """The filesystem stub's root, if `R2_LOCAL_DIR` names one."""
    e = os.environ if env is None else env
    raw = (e.get("R2_LOCAL_DIR") or "").strip()
    return Path(raw).expanduser().resolve() if raw else None


def load_dotenv(path=None) -> None:
    """Mac-side convenience: read `.env` so the push script needs no exports.

    `setdefault`, so a real environment variable always wins over the file.
    `.env` is gitignored as a whole file.
    """
    p = Path(path) if path else ROOT / ".env"
    if not p.exists() or os.environ.get("LOOP_NO_DOTENV"):
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))


# ------------------------------------------------------------------ backends

class _Backend:
    """The operations the lanes need. Both backends answer identically."""

    kind = "abstract"
    label = "abstract"

    def head(self, key: str) -> dict | None:
        """`{"key", "size", "sha256"}` for an existing object, else None."""
        raise NotImplementedError

    def get(self, key: str, dest) -> Path:
        raise NotImplementedError

    def put(self, path, key: str) -> dict:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    # -- shared ------------------------------------------------------------
    def same_as(self, path, key: str) -> tuple[bool, str]:
        """Is `key` already this exact file? Returns (verdict, why).

        Size first because it is free, then sha256, because two different cuts
        of the same episode can coincidentally match on length.
        """
        h = self.head(key)
        if h is None:
            return False, "not in the bucket"
        size = Path(path).stat().st_size
        if h["size"] != size:
            return False, f"size differs ({h['size']} shelved, {size} local)"
        if not h.get("sha256"):
            return False, ("no sha256 recorded on the object — re-uploading so "
                           "it gains one")
        local = sha256_file(path)
        if h["sha256"] != local:
            return False, f"sha256 differs ({h['sha256'][:12]}… vs {local[:12]}…)"
        return True, f"identical ({size:,} bytes, sha {local[:12]}…)"

    def _refuse_write(self, key: str):
        if dry_run():
            raise R2Unavailable(
                "DRY_RUN_WRITE_REFUSED",
                f"LOOP_DRY_RUN=1, so nothing was written to {key}",
                unblock="Unset LOOP_DRY_RUN to perform real writes.")

    # -- sidecar -----------------------------------------------------------
    def _meta_blob(self, path) -> bytes:
        path = Path(path)
        return (json.dumps({"sha256": sha256_file(path),
                            "size": path.stat().st_size}, indent=2)
                + "\n").encode()


class LocalBackend(_Backend):
    """The filesystem stub. Same key layout, same sidecars, no network."""

    kind = "local"

    def __init__(self, root: Path):
        # resolve() BOTH here and in _path(), or the escape guard fires on a
        # perfectly legal key: on macOS a temp dir is /var/… which resolves to
        # /private/var/…, so an unresolved root never prefix-matches its own
        # children and every put was rejected as escaping the stub.
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.label = f"local stub {self.root}"

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root)):
            raise R2Unavailable("BAD_KEY", f"key escapes the stub root: {key}")
        return p

    def head(self, key: str) -> dict | None:
        meta = self._path(key + META_SUFFIX)
        obj = self._path(key)
        if not obj.exists():
            return None
        sha = None
        if meta.exists():
            try:
                sha = json.loads(meta.read_text()).get("sha256")
            except json.JSONDecodeError:
                sha = None
        return {"key": key, "size": obj.stat().st_size, "sha256": sha}

    def get(self, key: str, dest) -> Path:
        src = self._path(key)
        if not src.exists():
            raise R2Unavailable("OBJECT_MISSING",
                                f"{key} is not in {self.label}")
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        return dest

    def put(self, path, key: str) -> dict:
        self._refuse_write(key)
        path = Path(path)
        dst = self._path(key)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dst)
        # Sidecar AFTER the object, exactly as the network backend does, so the
        # stub cannot pass a test the real thing would fail.
        self._path(key + META_SUFFIX).write_bytes(self._meta_blob(path))
        return {"key": key, "size": path.stat().st_size,
                "sha256": sha256_file(path)}

    def delete(self, key: str) -> None:
        self._refuse_write(key)
        for p in (self._path(key), self._path(key + META_SUFFIX)):
            if p.exists():
                p.unlink()


class WranglerBackend(_Backend):
    """Real R2, driven through the `wrangler r2 object` CLI."""

    kind = "r2"

    def __init__(self, account_id: str, bucket: str, token: str | None = None):
        self.account_id = account_id
        self.bucket = bucket
        self.label = f"r2://{bucket}"
        self._token = token          # never logged, never returned
        self._cmd = self._resolve_wrangler()

    @staticmethod
    def _resolve_wrangler() -> list[str]:
        if shutil.which("wrangler"):
            return ["wrangler"]
        if shutil.which("npx"):
            return list(WRANGLER_NPX)
        raise R2Unavailable(
            "WRANGLER_MISSING",
            "neither `wrangler` nor `npx` is on PATH, so R2 cannot be reached",
            unblock="Install Node, then `npm i -g wrangler@4` — or add a "
                    "`actions/setup-node` step to the workflow.")

    def _env(self) -> dict:
        # Explicit account id is what stops wrangler calling /memberships. See
        # THE TRAP at the top of this file.
        env = dict(os.environ, CLOUDFLARE_ACCOUNT_ID=self.account_id)
        if self._token:
            env["CLOUDFLARE_API_TOKEN"] = self._token
        return env

    def _run(self, args: list[str], ok_missing: bool = False, tries: int = 5):
        """Run one wrangler command. Returns the CompletedProcess.

        `ok_missing` lets a caller treat "no such key" as a normal answer while
        still turning an auth or network failure into a named stop — the
        distinction that keeps a broken credential from reading as an empty
        bucket.

        TRANSIENT FAILURES ARE RETRIED. wrangler does not retry a dropped
        connection: it exits 1 with `fetch failed`. Pushing the finished library
        is ~700 MB in forty-odd objects, and on the first real run object 13 of
        26 died that way — a whole shelf-load abandoned over one flaky socket.
        Only connectivity errors are retried; an auth error or a missing key is
        answered immediately, because retrying either is a wall.
        """
        blob = ""
        for attempt in range(1, tries + 1):
            r = subprocess.run([*self._cmd, *args], capture_output=True,
                               text=True, env=self._env(), timeout=1800)
            if r.returncode == 0:
                return r
            blob = (r.stdout or "") + (r.stderr or "")
            transient = ("fetch failed" in blob
                         or "connectivity" in blob
                         or "ECONNRESET" in blob
                         or "ETIMEDOUT" in blob
                         or "socket hang up" in blob)
            if not transient or attempt == tries:
                break
            # Backoff, not a fixed pause: a 100 MB render failed three attempts
            # five seconds apart and then succeeded on its own a minute later,
            # so the retry has to outlast a short outage, not just a blip.
            wait = 5 * (2 ** (attempt - 1))
            print(f"    … wrangler {args[2] if len(args) > 2 else ''} hit a "
                  f"network error; retry {attempt}/{tries - 1} in {wait}s",
                  flush=True)
            time.sleep(wait)
        if "10000" in blob or "Authentication error" in blob:
            raise R2Unavailable(
                "R2_AUTH_FAILED",
                "wrangler could not authenticate to Cloudflare (code 10000)",
                unblock="This is almost never the token's R2 permissions. "
                        "Confirm CLOUDFLARE_ACCOUNT_ID is set for this "
                        "process — without it wrangler calls /memberships, "
                        "which an R2-scoped token cannot read, and the error "
                        "is identical. See THE TRAP in loop/r2.py.")
        missing = ("does not exist" in blob or "10007" in blob
                   or "Not Found" in blob or "404" in blob)
        if ok_missing and missing:
            return None
        raise R2Unavailable(
            "R2_COMMAND_FAILED",
            f"wrangler {' '.join(args[:3])} failed (rc={r.returncode})",
            detail={"stderr": blob[-800:]},
            unblock="Check the bucket name and that the token carries R2 "
                    "read and write on this account.")

    def _obj(self, key: str) -> str:
        return f"{self.bucket}/{key}"

    def head(self, key: str) -> dict | None:
        """Fetch the sidecar. Present sidecar == object landed intact."""
        with tempfile.TemporaryDirectory() as td:
            dst = Path(td) / "meta.json"
            r = self._run(["r2", "object", "get", self._obj(key + META_SUFFIX),
                           "--file", str(dst), "--remote"], ok_missing=True)
            if r is None or not dst.exists():
                return None
            try:
                m = json.loads(dst.read_text())
            except json.JSONDecodeError:
                return None
        return {"key": key, "size": int(m.get("size", -1)),
                "sha256": m.get("sha256")}

    def get(self, key: str, dest) -> Path:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        r = self._run(["r2", "object", "get", self._obj(key),
                       "--file", str(dest), "--remote"], ok_missing=True)
        if r is None or not dest.exists():
            raise R2Unavailable("OBJECT_MISSING",
                                f"{key} is not in {self.label}",
                                unblock="Run bin/push-to-r2.sh on the Mac to "
                                        "shelve it, then re-run this lane.")
        return dest

    def put(self, path, key: str) -> dict:
        self._refuse_write(key)
        path = Path(path)
        self._run(["r2", "object", "put", self._obj(key), "--file", str(path),
                   "--content-type", content_type(path), "--remote"])
        # Sidecar second, so a sidecar can never advertise bytes that are not
        # there. A crash between the two costs one re-push, not a bad read.
        with tempfile.TemporaryDirectory() as td:
            m = Path(td) / "meta.json"
            m.write_bytes(self._meta_blob(path))
            self._run(["r2", "object", "put", self._obj(key + META_SUFFIX),
                       "--file", str(m), "--content-type", "application/json",
                       "--remote"])
        return {"key": key, "size": path.stat().st_size,
                "sha256": sha256_file(path)}

    def delete(self, key: str) -> None:
        self._refuse_write(key)
        self._run(["r2", "object", "delete", self._obj(key), "--remote"],
                  ok_missing=True)
        self._run(["r2", "object", "delete", self._obj(key + META_SUFFIX),
                   "--remote"], ok_missing=True)


# ------------------------------------------------------------------ resolver

def require(env=None) -> _Backend:
    """The backend to use, or `R2Unavailable` naming exactly what is absent.

    Order matters. The stub wins when `R2_LOCAL_DIR` is set, so a test can
    never accidentally reach the real bucket even with credentials present.
    """
    e = os.environ if env is None else env
    stub = local_dir(e)
    if stub is not None:
        return LocalBackend(stub)

    if dry_run():
        raise R2Unavailable(
            "DRY_RUN_NO_CREDENTIALS",
            "LOOP_DRY_RUN=1, so R2 credentials were deliberately not loaded",
            unblock="This is the expected dry-run outcome. Unset LOOP_DRY_RUN "
                    "for a real run, or set R2_LOCAL_DIR to rehearse against "
                    "the filesystem stub.")

    gone = missing_vars(e)
    if gone:
        raise R2Unavailable(
            "R2_CREDENTIALS_MISSING",
            "R2 is not configured: " + ", ".join(gone) +
            (" is not set" if len(gone) == 1 else " are not set"),
            detail={"missing": gone, "required": list(REQUIRED_VARS)},
            unblock="Follow docs/CLOUD-UPLOAD-SETUP.md, then set "
                    + " and ".join(gone) +
                    " (repo secrets in Actions, .env or a wrangler login on "
                    "the Mac).")
    return WranglerBackend(e["CLOUDFLARE_ACCOUNT_ID"].strip(),
                           bucket_name(e),
                           (e.get("CLOUDFLARE_API_TOKEN") or "").strip() or None)


def have_assets(backend: _Backend, slug: str) -> bool:
    """Is this episode fully shelved — render AND thumbnail?

    Both or neither. Pulling a render whose thumbnail never arrived produces an
    upload with no card, and the scopes this credential carries cannot fix a
    thumbnail after the fact without a second, wider consent.
    """
    return (backend.head(render_key(slug)) is not None
            and backend.head(thumb_key(slug)) is not None)


def inventory(backend: _Backend, slugs) -> list[dict]:
    """What is on the shelf, for a known list of slugs.

    There is deliberately no LIST here. `wrangler r2 object` has no list
    verb, and inventing one from a stored index would be a second list that
    could disagree with the bucket — the "two components each keeping their own
    list with no link" defect. The slugs come from
    research/publish_order.json, which is the only list that matters.
    """
    out = []
    for s in slugs:
        r, t = backend.head(render_key(s)), backend.head(thumb_key(s))
        out.append({"slug": s, "render": r, "thumbnail": t,
                    "ready": r is not None and t is not None})
    return out


# ---------------------------------------------------------------------- CLI

def _publish_slugs() -> list[str]:
    """Every domain's queue, not just deep sea's.

    This read research/publish_order.json BY NAME and drives BOTH push() and
    push_shorts(), so nothing from materials-and-manufacturing had ever been
    shelved -- not one render, not one Short. The cloud upload lane and the
    cloud Shorts lane both read from R2, so both were structurally incapable of
    publishing a materials episode; the three that are scheduled got there
    because the Mac's own backfill lane uploads directly.

    Third instance of this exact defect found on 2026-09-05, after
    loop/shorts_lane.py and before this one. loop/batch_queue.py exists to be
    the single definition; V27 now asks this module too.
    """
    import batch_queue                                     # noqa: PLC0415
    return batch_queue.queued_slugs()


def push(backend: _Backend, slugs=None, force: bool = False) -> dict:
    """Shelve every finished render and thumbnail that is not already up there.

    IDEMPOTENT, AND BY CONTENT. An object is skipped only when its size AND its
    sha256 match the file on this disk — never because a key of that name
    exists. A re-cut episode keeps its slug, so name-matching would leave the
    old cut on the shelf and the cloud lane would publish it.

    Every skip prints its reason. A push that says nothing is indistinguishable
    from a push that did nothing.
    """
    renders = ROOT / "renders"
    thumbs = ROOT / "channel" / "thumbnails"
    slugs = list(slugs) if slugs else _publish_slugs()
    # A render the gate holds is never shelved, by either route: the cloud
    # upload lane takes whatever is on the shelf, so refusing it here is what
    # keeps a sub-floor or clipped render off YouTube. See loop/render_gate.py.
    import render_gate                                     # noqa: PLC0415
    held = render_gate.held_slugs()
    for h in [x for x in slugs if x in held]:
        print(f"  HELD {h}: refused by the render gate, not shelved")
    slugs = [x for x in slugs if x not in held]
    sent, skipped, absent = [], [], []

    for slug in slugs:
        for local, key, what in ((renders / f"{slug}-final.mp4",
                                  render_key(slug), "render"),
                                 (thumbs / f"{slug}.jpg",
                                  thumb_key(slug), "thumbnail")):
            if not local.exists():
                absent.append(f"{slug} {what}: not built on this Mac yet")
                print(f"  ·  skip {slug} {what}: not built yet")
                continue
            if not force:
                same, why = backend.same_as(local, key)
                if same:
                    skipped.append(f"{slug} {what}: {why}")
                    print(f"  =  skip {slug} {what}: already shelved, {why}")
                    continue
            else:
                why = "forced"
            print(f"  ↑  push {slug} {what} ({local.stat().st_size:,} bytes) "
                  f"— {why}", flush=True)
            r = backend.put(local, key)
            sent.append(f"{slug} {what}: {r['size']} bytes, "
                        f"sha {r['sha256'][:12]}…")
    return {"pushed": sent, "skipped": skipped, "absent": absent}


def verify_shorts() -> tuple[bool, list[str]]:
    """Run V14 (attribution) and V15 (caption crop) over `shorts/`.

    WHY THIS IS A PRECONDITION OF SHELVING, AND NOT A CI STEP.

    Both validators read the finished pixels with **Apple's Vision framework**,
    through `research/imagery_video.py:ocr`, which compiles a small Swift helper
    with `swiftc`. Neither exists on a Linux GitHub runner. So the choice was:

      (a) cut Shorts in Actions and skip V14/V15 there — REJECTED. An unrun
          validator is not a passing one, and shipping an uncredited Short on a
          monetised channel is the single thing this pipeline may not do.
      (b) cut in Actions and OCR with tesseract instead — REJECTED. A different
          engine, unproven against these fonts, guarding the one check that may
          not be wrong.
      (c) cut and VERIFY on the Mac, which has Vision, then shelve; the cloud
          only uploads what already passed. CHOSEN.

    That is the same shape as the episodes: the Mac renders in a batch every
    ~7.5 weeks and shelves the result, and everything SCHEDULED runs in the
    cloud. Attribution is verified on the machine that can actually read the
    pixels, and a Short that fails is never shelved, so the cloud lane can only
    ever publish a verified one.

    Returns `(ok, lines)`. Never raises: a validator that cannot import is a
    failure, not a crash, and certainly not a pass.
    """
    sys.path.insert(0, str(ROOT / "loop"))
    lines = []
    try:
        import validate as V                                # noqa: PLC0415
    except Exception as e:                                  # noqa: BLE001
        return False, [f"loop/validate.py could not be imported: {e}"]
    ok = True
    for fn in (V.v14_shorts_attribution, V.v15_shorts_caption_crop):
        try:
            r = fn()
        except Exception as e:                              # noqa: BLE001
            ok = False
            lines.append(f"{fn.__name__} CRASHED: {e}")
            continue
        good = not r.failures
        ok = ok and good
        lines.append(f"{r.name}: {'PASS' if good else 'FAIL'} "
                     f"(examined {r.examined})")
        for f in r.failures[:5]:
            lines.append(f"    {f}")
    return ok, lines


def receipt_refuses(rec: Path) -> str | None:
    """Why a cut's own receipt says it must not ship, or None if it may.

    visuals/shorts.py:verify writes {"ok": bool, "problems": [...]} into
    <cut>.short.json. A receipt that cannot be read is a refusal too: the
    receipt is the only record of which beats were used and who is credited,
    and a Short whose record is unreadable is a Short nobody can vouch for.
    """
    try:
        d = json.loads(Path(rec).read_text())
    except (OSError, ValueError) as e:
        return f"receipt unreadable ({e.__class__.__name__})"
    if d.get("ok") is False:
        probs = d.get("problems") or ["no reason recorded"]
        return "ok=false: " + "; ".join(str(p) for p in probs)
    return None


def push_shorts(backend: _Backend, slugs=None, force: bool = False) -> dict:
    """Shelve every cut Short — but only after V14 and V15 pass.

    The gate is on the WHOLE directory, not per file, because that is how the
    validators work: they read every receipt in `shorts/`. One uncredited cut
    blocks the shelf until it is fixed or removed, which is the correct
    severity for the one rule this pipeline may not break.
    """
    ok, lines = verify_shorts()
    for line in lines:
        print(f"  {line}")
    if not ok:
        raise R2Unavailable(
            "SHORTS_UNVERIFIED",
            "V14 (attribution) or V15 (caption crop) failed, so no Short was "
            "shelved",
            detail={"report": lines},
            unblock="Fix or delete the offending cut in shorts/ and re-run. "
                    "Nothing reaches R2 — and therefore nothing reaches "
                    "YouTube — until both validators are green, because the "
                    "Linux runner has no Apple Vision and cannot re-check "
                    "this later.")

    shorts = ROOT / "shorts"
    slugs = list(slugs) if slugs else _publish_slugs()
    sent, skipped, absent, refused = [], [], [], []
    import shorts_lane                                    # noqa: PLC0415
    for slug, rank in ((s_, r_) for s_ in slugs
                       for r_ in range(1, shorts_lane.cuts_for(s_) + 1)):
        name = shorts_lane.short_file(slug, rank)
        mp4 = shorts / name
        rec = shorts / f"{name}.short.json"
        if not mp4.exists() or not rec.exists():
            if rank == 1:
                absent.append(f"{slug}: no rank-1 cut with a receipt")
                print(f"  ·  skip {slug} short: not cut yet")
            # A deeper rank that was never cut is not a gap: an episode with
            # one self-contained idea has no rank 2 (visuals/shorts.py).
            continue
        slug_label = shorts_lane.Pick(slug, rank).label
        why_bad = receipt_refuses(rec)
        if why_bad:
            # THE CUT'S OWN VERIFIER SAID NO. visuals/shorts.py writes
            # ok:false and the problems into the receipt, prints BAD, exits 1
            # -- and until 2026-09-18 nothing downstream read any of it, so a
            # refused cut would have been shelved and published like a good
            # one. V14/V15 above prove the credit and the crop; this proves
            # the cut itself. Loud every night until it is fixed or re-cut.
            refused.append(f"{slug_label}: {why_bad}")
            print(f"  ✗  refuse {slug_label} short: its own receipt says {why_bad}")
            continue
        for local, key, what in ((mp4, short_key(slug, rank), "short"),
                                 (rec, short_receipt_key(slug, rank), "receipt")):
            if not force:
                same, why = backend.same_as(local, key)
                if same:
                    skipped.append(f"{slug_label} {what}: {why}")
                    print(f"  =  skip {slug_label} {what}: already shelved, {why}")
                    continue
            else:
                why = "forced"
            print(f"  ↑  push {slug_label} {what} ({local.stat().st_size:,} bytes) "
                  f"— {why}", flush=True)
            r = backend.put(local, key)
            sent.append(f"{slug_label} {what}: {r['size']} bytes")
    if refused:
        print(f"  {len(refused)} Short(s) refused by their own receipt; re-cut "
              f"or fix visuals/shorts.py, they are not shelved and will not "
              f"publish: " + "; ".join(refused))
    return {"pushed": sent, "skipped": skipped, "absent": absent,
            "refused": refused, "verified": lines}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Cloudflare R2 shelf for finished renders (via wrangler).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="which backend resolves, and what is shelved")
    p_push = sub.add_parser("push", help="shelve renders + thumbnails")
    p_push.add_argument("slugs", nargs="*",
                        help="default: every slug in research/publish_order.json")
    p_push.add_argument("--force", action="store_true",
                        help="re-upload even when size and sha256 match")
    p_ps = sub.add_parser("push-shorts",
                          help="shelve cut Shorts, gated on V14 + V15")
    p_ps.add_argument("slugs", nargs="*")
    p_ps.add_argument("--force", action="store_true")
    p_put = sub.add_parser("put"); p_put.add_argument("path"); p_put.add_argument("key")
    p_get = sub.add_parser("get"); p_get.add_argument("key"); p_get.add_argument("dest")
    p_hd = sub.add_parser("head"); p_hd.add_argument("key")
    p_rm = sub.add_parser("delete"); p_rm.add_argument("key")
    a = ap.parse_args(argv)

    load_dotenv()
    try:
        b = require()
    except R2Unavailable as e:
        print(f"NAMED STOP [{e.code}] {e.message}")
        if e.unblock:
            print(f"  unblock: {e.unblock}")
        return 3

    try:
        if a.cmd == "check":
            rows = inventory(b, _publish_slugs())
            ready = [r for r in rows if r["ready"]]
            print(f"backend : {b.label}")
            print(f"shelved : {len(ready)} of {len(rows)} queued episode(s)")
            for r in rows:
                mark = "✓" if r["ready"] else ("·" if not r["render"] else "!")
                size = r["render"]["size"] if r["render"] else 0
                print(f"  {mark} {size:>12,}  {r['slug']}")
            return 0
        if a.cmd == "push":
            print(f"shelf: {b.label}")
            r = push(b, a.slugs, force=a.force)
            print(f"\npushed {len(r['pushed'])}, "
                  f"skipped {len(r['skipped'])} already identical, "
                  f"{len(r['absent'])} not built yet")
            # Rule 0: a push that shelved nothing AND had nothing to shelve is
            # not a success, it is an empty run wearing a green tick.
            if not r["pushed"] and not r["skipped"]:
                print("NAMED STOP [NOTHING_TO_PUSH] no render or thumbnail "
                      "exists on this Mac for any queued episode.")
                print("  unblock: run bin/render-all.sh / bin/assemble-all.sh "
                      "first.")
                return 3
            return 0
        if a.cmd == "push-shorts":
            print(f"shelf: {b.label}")
            print("  verifying attribution on this Mac before anything is "
                  "shelved (the Linux runner cannot):")
            r = push_shorts(b, a.slugs, force=a.force)
            print(f"\npushed {len(r['pushed'])}, "
                  f"skipped {len(r['skipped'])} already identical, "
                  f"{len(r['absent'])} not cut yet")
            if not r["pushed"] and not r["skipped"]:
                print("NAMED STOP [NO_SHORTS_CUT] no rank-1 Short with a "
                      "receipt exists for any queued episode.")
                print("  unblock: bin/make-shorts.sh --all")
                return 3
            return 0
        if a.cmd == "head":
            h = b.head(a.key)
            print(json.dumps(h, indent=2) if h else f"{a.key}: not shelved")
            return 0
        if a.cmd == "put":
            r = b.put(a.path, a.key)
            print(f"put {r['key']}  {r['size']:,} bytes  sha {r['sha256'][:12]}…")
            return 0
        if a.cmd == "get":
            b.get(a.key, a.dest)
            print(f"got {a.key} -> {a.dest}")
            return 0
        if a.cmd == "delete":
            b.delete(a.key)
            print(f"deleted {a.key} (and its sidecar)")
            return 0
    except R2Unavailable as e:
        print(f"NAMED STOP [{e.code}] {e.message}")
        if e.unblock:
            print(f"  unblock: {e.unblock}")
        return 3
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
