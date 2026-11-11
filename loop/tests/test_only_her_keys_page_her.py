"""Only her own key or account pages her (hostile review 2026-11-02, finding 4).

  1. A stop whose own words start "Nothing" never pages (exit 0), even under a
     code no policy lists; the same code with any other message still exits 3.
  2. Every owner_action code is a credential, key, scope, channel or account.
  3. The digest names an action for her only for owner_action; any other stop
     (a Mac batch, a defect) has none, so the subject never says "needs you".
bin/loop-stage.sh's mention rule is held by test_held_stops.py.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, LOOP)
os.environ["LOOP_STOPS_DIR"] = tempfile.mkdtemp(prefix="herkeys-")

import common  # noqa: E402
import digest  # noqa: E402

CREDENTIAL = re.compile(r"KEY|OAUTH|TOKEN|CREDENTIAL|SCOPE|CHANNEL|LOCKED|ARMED|ACCOUNT")
# Her hardware, not a key: the Mac that runs the night batch must be awake.
# And her own voice (6 Nov 2026): the Whisper Almanac sample only she can record.
# And her phone (11 Nov 2026): only she can take the youtube.com/verify code.
HER_HARDWARE = {"DELEGATED_HARVEST_STALE", "WHISPER_SAMPLE_MISSING", "WHISPER_SAMPLE_UNUSABLE",
                "WHISPER_LONG_UPLOADS_NOT_ALLOWED"}


def rc_of(code: str, message: str, unblock: str = "") -> int:
    try:
        with common.Stage("zz-test-stage", "2026-W45") as st:
            st.named_stop(code, message, unblock=unblock)
    except SystemExit as e:
        return int(e.code or 0)
    return -1


def main() -> int:
    fails = []
    if rc_of("ZZ_UNLISTED_TEST", "the runway is full.", unblock="Nothing to run.") != 0:
        fails.append("a stop that says 'Nothing to run' still paged")
    if rc_of("ZZ_UNLISTED_TEST4", "Nothing is on the shelf because a lane broke.",
             unblock="Find the lane and fix it.") != 3:
        fails.append("a defect whose MESSAGE starts 'Nothing' stopped paging")
    if rc_of("ZZ_UNLISTED_TEST2", "the runway is short.", unblock="Nothing to do; it refills itself.") != 0:
        fails.append("a stop whose instruction says 'Nothing to do' still paged")
    if rc_of("ZZ_UNLISTED_TEST3", "the upload failed with HTTP 500.") != 3:
        fails.append("negative: an unlisted defect no longer pages at all")
    pol = json.load(open(os.path.join(LOOP, "stop_policy.json")))
    bad = [c for c in pol.get("owner_action", {}) if not c.startswith("_")
           and not CREDENTIAL.search(c) and c not in HER_HARDWARE]
    if bad:
        fails.append(f"owner_action codes that are not her key or account: {bad}")
    if not [c for c in pol.get("owner_action", {}) if not c.startswith("_")]:
        fails.append("examined no owner_action codes")
    if digest.action_for({"code": "MAC_NOT_SHIPPING", "stage": "batch",
                          "disposition": "needs_human"}) is not None:
        fails.append("the digest names an action for her on a Mac stop")
    if not digest.action_for({"code": "OAUTH_EXPIRED", "disposition": "owner_action"}):
        fails.append("negative: her expired sign-in no longer names an action")
    for f in fails:
        print("FAIL:", f)
    print(f"{'FAIL' if fails else 'PASS'}: only her keys page her")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())

