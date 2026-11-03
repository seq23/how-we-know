"""An owner-approved render is never moved aside: the picture-floor heal skips
it while its bytes are the approved ones, and moves a DIFFERENT cut as before."""
import hashlib, json, os, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["LOOP_DRY_RUN"] = "1"
import approved_renders as AR  # noqa: E402

fails = []
with tempfile.TemporaryDirectory() as td:
    r = Path(td)
    f = r / "ep-final.mp4"
    f.write_bytes(b"approved cut")
    real = AR.STORE
    AR.STORE = r / "approved.json"
    AR.STORE.write_text(json.dumps({"ep": {"sha256": hashlib.sha256(b"approved cut").hexdigest(),
                                           "bytes": len(b"approved cut")}}))
    if not AR.protected("ep", r):
        fails.append("the approved bytes are not protected")
    f.write_bytes(b"another cut!")
    if AR.protected("ep", r):
        fails.append("a different cut of the same length is protected")
    if AR.protected("other", r):
        fails.append("an episode with no approval is protected")
    AR.STORE = real
for x in fails:
    print("FAIL:", x)
print("approved render:", "FAILED" if fails else "ok")
sys.exit(1 if fails else 0)
