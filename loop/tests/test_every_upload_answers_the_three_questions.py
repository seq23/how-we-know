"""Every upload path answers YouTube's three questions the way the owner decided.

Owner, 14 Sep 2026: allow embedding; AI use — No; paid promotion — No. Set at upload, on every
lane, so nothing has to be fixed in Studio again. Four lanes upload (Mac backfill, cloud upload,
Mac Shorts, cloud Shorts) through two payload builders and one resumable-upload call; this proves
the builders carry all three, the upload URL names the part that carries the paid-promotion
answer (the API silently drops a part it was not told about), and every lane goes through them.

Hard-fails if it examines fewer than two builders or four lanes.
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, LOOP)
import shorts_lane                                                 # noqa: E402
import upload                                                      # noqa: E402

fails: list[str] = []
WANT_STATUS = {"embeddable": True, "containsSyntheticMedia": False}
WANT_PAID = {"hasPaidProductPlacement": False}

# Build with the real signatures, against a real script from the repository.
import glob                                                        # noqa: E402
script = sorted(glob.glob(os.path.join(LOOP, "..", "scripts", "*.md")))[0]
slug = os.path.basename(script)[:-3]
long_form = upload.build_payload({"slug": slug, "question": slug.split("-", 1)[-1].replace("-", " "),
                                  "script": os.path.relpath(script, os.path.join(LOOP, ".."))})
short = shorts_lane.build_payload("t-slug", "what is a test")
examined = 0
for name, payload in (("upload.build_payload", long_form), ("shorts_lane.build_payload", short)):
    examined += 1
    st = payload.get("status", {})
    for k, v in WANT_STATUS.items():
        if st.get(k) is not v:
            fails.append(f"{name}: status.{k} is {st.get(k)!r}, owner decided {v!r}")
    paid = payload.get("paidProductPlacementDetails", {})
    for k, v in WANT_PAID.items():
        if paid.get(k) is not v:
            fails.append(f"{name}: paidProductPlacementDetails.{k} is {paid.get(k)!r}, owner decided {v!r}")

if "paidProductPlacementDetails" not in upload.UPLOAD_URL:
    fails.append("upload.UPLOAD_URL does not name the paidProductPlacementDetails part, so the paid-promotion answer is dropped on insert")
if "status" not in upload.UPLOAD_URL:
    fails.append("upload.UPLOAD_URL does not name the status part")

# Every lane goes through the builders, not a payload of its own.
lanes = {"backfill.py": r"up\.build_payload\(", "shorts_lane.py": r"\bbuild_payload\(",
         "cloud_upload.py": r"up\.build_payload\(|upload_one\(|backfill", "shorts_cloud.py": r"shorts_lane\.upload_short|upload_short\("}
seen = 0
for fname, pattern in lanes.items():
    src = open(os.path.join(LOOP, fname)).read()
    seen += 1
    if not re.search(pattern, src):
        fails.append(f"{fname} no longer uploads through the shared builder (looked for /{pattern}/)")
    if '"status": {' in src and fname not in ("upload.py", "shorts_lane.py"):
        fails.append(f"{fname} builds its own status payload; the three answers would have to be kept in two places")

if examined < 2 or seen < 4:
    fails.append("Rule 0: fewer than two builders or four lanes examined")
if fails:
    for f in fails:
        print(f"FAIL {f}")
    sys.exit(1)
print(f"PASS: {examined} payload builders carry embedding=on, AI use=No, paid promotion=No; {seen} lanes upload through them")
