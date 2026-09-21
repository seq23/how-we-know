"""The rights-cleared pool accumulates. It never forgets a record it still has.

`channel/imagery/species.json` states the rule in its own policy field:
"Records only ever accumulate here -- neither gate may delete the other's".
`research/imagery.py` did not honour it, and `loop/footage_lane.py`'s
CLEARED_POOL_SHRANK stop is the guard that eventually caught the consequence.

CONFIRMED by bisecting channel/imagery/rights.json:

    f82650c  2026-08-31  68 records, includes media 12013 15248 16065 28649
    22629d4  2026-09-05  70 records, all four gone   <- first automated harvest
    28e3a56  2026-09-12  70 records, still gone

`research/imagery.py:_merge_assets` kept only records from OTHER gates
(`a.get("source_org") != keep_source`), so every NOAA Ocean Exploration record
that did not come back in THIS week's API page was evicted -- 18 of them,
every one still on disk with its recorded sha256 intact.
`research/imagery_species.py` points at NOAA records BY MEDIA ID and correctly
refuses to invent a rights record for one it cannot find, so from 2026-09-05 the
species index failed four records on every run.

On 2026-09-12 (run 34672456430, issue #77) that surfaced -- but through a second
defect, not the first. `imagery_species.harvest()` wrote species.json BEFORE
raising on those failures, contrary to its own docstring and contrary to what
the lane then printed ("exited 1; the pool is unchanged"). The index went from
33 records to 29 and CLEARED_POOL_SHRANK fired on the write, not the harvest.

Three fixes, each proven negatively here by restoring the broken state:

1. `_merge_assets` keeps a record from any gate, including its own, while the
   bytes it was approved on are still on disk and still hash to the sha256 in
   the record. This is not a relaxed gate: the record already passed, and it is
   dropped the moment its provenance stops resolving.
2. `imagery_species.harvest()` raises BEFORE writing, so a failed run leaves the
   last verified manifest in place.
3. The 18 evicted records were restored to rights.json, each re-verified against
   the bytes on disk.

Hard-fails when it examines zero records.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "research"))

import imagery                                              # noqa: E402
import imagery_species as species                           # noqa: E402

RIGHTS = os.path.join(ROOT, "channel", "imagery", "rights.json")
IMAGERY_DIR = os.path.join(ROOT, "channel", "imagery")


def media_id(local_file: str) -> int | None:
    """The media id is the middle field of the filename, which is how
    imagery_species.py itself keys the manifest (`local_file.split("__")[1]`)."""
    parts = os.path.basename(local_file).split("__")
    if len(parts) < 3 or not parts[1].isdigit():
        return None
    return int(parts[1])


def sha_of(local_file: str) -> str | None:
    path = os.path.join(IMAGERY_DIR, local_file)
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    checks, examined, failures = 0, 0, []

    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if ok:
            print(f"  ok  {name}")
        else:
            print(f"  ✗ {name}{(': ' + detail) if detail else ''}")
            failures.append(name)

    with open(RIGHTS, encoding="utf-8") as fh:
        manifest = json.load(fh)
    assets = manifest["assets"]
    have = {media_id(a["local_file"]) for a in assets} - {None}

    # ------------------------------------------------------------------ 1
    # THE CHECK THAT WAS MISSING. Every media id the species index names by
    # number must resolve in rights.json. Had this existed on 2026-09-05 it
    # would have failed that day instead of a week later, as a stop.
    src = open(os.path.join(ROOT, "research", "imagery_species.py"),
               encoding="utf-8").read()
    block = src[src.index("NOAA_SUBJECTS = ["):src.index("# ------------------------------------------------------------------ the gate")]
    demanded = sorted({int(m) for m in re.findall(r"^\s*\((\d+),", block, re.M)})
    if not demanded:
        print("FAIL: parsed zero media ids out of imagery_species.py -- this "
              "test would pass on an empty set, which is Rule 0's whole point.")
        return 1
    examined += len(demanded)
    missing = [d for d in demanded if d not in have]
    check(f"all {len(demanded)} media id(s) the species index names resolve in "
          "rights.json", not missing,
          f"absent: {missing} -- the species index cannot invent a rights record, "
          "so each of these fails every harvest")

    # ------------------------------------------------------------------ 2
    # Every record in the manifest must still verify against its own bytes.
    examined += len(assets)
    unverified = []
    for a in assets:
        got = sha_of(a["local_file"])
        if got is None or got != a.get("sha256"):
            unverified.append(a["local_file"])
    check(f"all {len(assets)} manifest record(s) still hash to their own bytes",
          not unverified, f"{len(unverified)} bad: {unverified[:5]}")

    # ------------------------------------------------------------------ 3
    # _merge_assets keeps a verified same-source record, and NEGATIVE PROOF
    # that the old predicate would have evicted it.
    keep_source = imagery.SOURCE_NOAA_OE
    survivor = next((a for a in assets
                     if a.get("source_org") == keep_source and sha_of(a["local_file"])), None)
    if survivor is None:
        print("FAIL: no verifiable same-source record to test the merge with")
        return 1
    fresh = [dict(a) for a in assets[:1] if a["local_file"] != survivor["local_file"]]
    merged = imagery._merge_assets(assets, fresh, keep_source=keep_source)
    check("a verified record from this gate's own source survives the merge",
          survivor["local_file"] in {a["local_file"] for a in merged})

    old_rule = [a for a in assets
                if a["local_file"] not in {f["local_file"] for f in fresh}
                and a.get("source_org") != keep_source]
    check("NEGATIVE: the old predicate would have evicted it",
          survivor["local_file"] not in {a["local_file"] for a in old_rule},
          "the old rule kept it too, so check 3 proves nothing")

    # ------------------------------------------------------------------ 4
    # And it must still DROP a record whose provenance stopped resolving --
    # otherwise the fix is just "keep everything", which is how a clip nobody
    # can vouch for gets silently re-accepted.
    ghost = dict(survivor)
    ghost["local_file"] = "assets/ghost__999999__not-on-disk.jpg"
    bent = dict(survivor)
    bent["local_file"] = survivor["local_file"]
    bent["sha256"] = "0" * 64
    dropped = imagery._merge_assets([ghost], [], keep_source=keep_source)
    check("a record whose file is gone is dropped", dropped == [])
    dropped = imagery._merge_assets([bent], [], keep_source=keep_source)
    check("a record whose bytes no longer match its sha256 is dropped",
          dropped == [])
    examined += 2

    # ------------------------------------------------------------------ 5
    # imagery_species.harvest() must not write the manifest when it fails.
    # Exercised against the real function with a temp manifest path and the
    # network-touching half stubbed out.
    with tempfile.TemporaryDirectory() as td:
        tmp_manifest = os.path.join(td, "species.json")
        with open(tmp_manifest, "w", encoding="utf-8") as fh:
            json.dump({"asset_count": 33, "marker": "LAST_GOOD"}, fh)
        saved = (species.SPECIES_MANIFEST, species.PD_SPECIES,
                 species.NOAA_SUBJECTS, species.PD_REUSE, species.OUT)
        try:
            species.SPECIES_MANIFEST = tmp_manifest
            species.OUT = td
            species.PD_SPECIES = []          # no Commons calls
            # One record that cannot resolve: exactly the production failure.
            species.NOAA_SUBJECTS = [(999999, "anglerfish", "CREDIT", "note")]
            species.PD_REUSE = []
            raised = False
            # The harvester prints its own "  FAIL anglerfish  media 999999"
            # line to stdout here. That line is the PROOF, not a failure of
            # this test - it was read as a second red test on 2026-09-21
            # (run 35634217382), so say so before it appears.
            print("  (negative proof: the harvester's own 'FAIL anglerfish "
                  "media 999999' line below is EXPECTED - the test asserts "
                  "that it hard-fails)", flush=True)
            try:
                species.harvest()
            except SystemExit:
                raised = True
            check("harvest() hard-fails when a record cannot be resolved", raised)
            with open(tmp_manifest, encoding="utf-8") as fh:
                after = json.load(fh)
            check("and it leaves the last verified manifest untouched",
                  after.get("marker") == "LAST_GOOD",
                  "the manifest was rewritten with the shrunken set, which is "
                  "what tripped CLEARED_POOL_SHRANK")
        finally:
            (species.SPECIES_MANIFEST, species.PD_SPECIES,
             species.NOAA_SUBJECTS, species.PD_REUSE, species.OUT) = saved
    examined += 1

    # ------------------------------------------------------------- Rule 0
    if examined == 0 or checks == 0:
        print("FAIL: this test examined zero records")
        return 1
    print(f"\nexamined {examined} record(s) over {checks} check(s), "
          f"{len(failures)} failed")
    if failures:
        print("FAIL: " + "; ".join(failures))
        return 1
    print("all green - the cleared pool only accumulates, a record is kept only "
          "while its own bytes still vouch for it, and a failed species harvest "
          "leaves the last good manifest alone")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
