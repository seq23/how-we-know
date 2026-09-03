"""auth/check_ci_scopes.py must name the exact scope missing from the CI
YouTube credential, asserted against T.SCOPES only, never a second list.

CONFIRMED 2026-09-03: `loop-reach` failed with CAPTIONS_SCOPE_MISSING because
the repo secret `YT_OAUTH_REFRESH_TOKEN` was minted a day before
`youtube.force-ssl` was added to `auth/tokens.py:T.SCOPES`, and nothing
checked the CI credential against the CURRENT scope list — only
`auth/youtube_auth.py`'s local-token guard existed, and its reach stopped at
`.secrets/`.

This cannot hit Google's real endpoints from a test, so it proves the part
that matters without a network call: `missing_scopes()` compares whatever
scopes a credential actually carries against `T.SCOPES` and returns exactly
the difference — no hardcoded scope list of its own to drift out of sync with
`auth/tokens.py`, which would be the exact defect one level up.

Hard-fails when it examines zero cases.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "auth"))

import check_ci_scopes as C  # noqa: E402
import tokens as T            # noqa: E402


def check() -> tuple[int, list[str]]:
    examined = 0
    fails: list[str] = []

    # ---- every scope present -> nothing missing ----------------------------
    examined += 1
    m = C.missing_scopes(list(T.SCOPES))
    if m:
        fails.append(f"missing_scopes() found {m!r} when every T.SCOPES "
                     f"entry was granted")

    # ---- exactly one scope missing -> names THAT one, and only that one ----
    for target in T.SCOPES:
        examined += 1
        granted = [s for s in T.SCOPES if s != target]
        m = C.missing_scopes(granted)
        if m != [target]:
            fails.append(f"with only {target!r} withheld, missing_scopes() "
                         f"returned {m!r}, expected exactly [{target!r}]")

    # ---- the real 2026-09-03 shape: force-ssl specifically missing --------
    examined += 1
    force_ssl = "https://www.googleapis.com/auth/youtube.force-ssl"
    assert force_ssl in T.SCOPES, "test assumption stale: force-ssl left T.SCOPES"
    granted = [s for s in T.SCOPES if s != force_ssl]
    m = C.missing_scopes(granted)
    if m != [force_ssl]:
        fails.append(f"the real incident's exact shape (force-ssl withheld) "
                     f"produced {m!r}, expected [{force_ssl!r}]")

    # ---- nothing granted at all -> everything is missing -------------------
    examined += 1
    m = C.missing_scopes([])
    if set(m) != set(T.SCOPES):
        fails.append(f"granting nothing should report every T.SCOPES entry "
                     f"missing; got {m!r}")

    # ---- T.SCOPES is the ONLY source of truth: change it, the check follows
    examined += 1
    original = list(T.SCOPES)
    try:
        T.SCOPES.append("https://www.googleapis.com/auth/made-up-for-this-test")
        m = C.missing_scopes(original)
        if T.SCOPES[-1] not in m:
            fails.append("adding a scope to T.SCOPES did not make "
                         "missing_scopes() start requiring it - "
                         "check_ci_scopes.py may hold its own copy of the "
                         "scope list instead of asserting against T.SCOPES, "
                         "which is the exact defect this guards against one "
                         "level up")
    finally:
        T.SCOPES[:] = original

    # ---- the token itself is never printed anywhere in the module's text --
    examined += 1
    src = open(os.path.join(ROOT, "auth", "check_ci_scopes.py"),
              encoding="utf-8").read()
    for bad in ("print(access_token", "print(creds[", "print(refresh"):
        if bad in src:
            fails.append(f"check_ci_scopes.py contains {bad!r} - a credential "
                         f"must never be printed, even truncated")

    return examined, fails


def main() -> int:
    examined, fails = check()
    if examined == 0:
        print("FAIL: examined zero CI-scope-check cases")
        return 1
    print(f"inspected {examined} CI-scope-check case(s)")
    for f in fails:
        print(f"  ✗ {f}")
    if fails:
        print(f"{len(fails)} failure(s)")
        return 1
    print("all green - the CI scope check names exactly the scope missing, "
         "asserted against T.SCOPES alone")
    return 0


if __name__ == "__main__":
    sys.exit(main())
