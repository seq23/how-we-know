"""Moving-footage evidence carried from a master to its Short receipt."""
from __future__ import annotations
import json
from pathlib import Path

CODE = "SHORT_MASTER_NO_FOOTAGE"

class NoMasterFootage(ValueError):
    pass


def evidence(master) -> dict:
    master = Path(master)
    try:
        rec = json.loads(Path(f"{master}.footage.json").read_text())
    except (OSError, ValueError):
        raise NoMasterFootage(f"{CODE}: {master.stem}: no footage record; retry after the footage master is built")
    beats = rec.get("beats") or {}
    if rec.get("footage_beats_expected") == 0 or not any(beats.values()):
        raise NoMasterFootage(f"{CODE}: {master.stem}: no moving footage; retry after the footage master is built")
    st = master.stat()
    stamp = {"bytes": st.st_size, "mtime": int(st.st_mtime)}
    if rec.get("master") != stamp:
        raise NoMasterFootage(f"{CODE}: {master.stem}: stale footage record; retry after the matching record exists")
    return {"master": stamp, "footage_beats": sum(bool(v) for v in beats.values()),
            "master_sha256": rec.get("master_sha256")}


def receipt_ok(rec) -> bool:
    proof = (rec or {}).get("master_footage") or {}
    return bool(proof.get("master") and proof.get("footage_beats", 0) > 0)
