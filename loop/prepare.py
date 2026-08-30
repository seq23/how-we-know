"""Freeze the approved week into immutable work copies under `loop/work/`.

Why a copy rather than voicing `scripts/*.md` directly:

* The owner's Monday choice may be the POV **bank** line rather than the
  editorial paraphrase currently written into the script. That substitution has
  to happen somewhere, and it must not be a write into `scripts/` — those files
  are the authored record, edited by people, and a pipeline that rewrites them
  under a scheduler will eventually clobber an edit.
* A week's render input should be a snapshot. If someone edits a script on
  Wednesday, Thursday's upload still corresponds to what was voiced on Tuesday.

Nothing else is changed: narration is copied word for word, and every directive
line is preserved exactly, so the pipeline's truth guard still governs.
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import LOOP, ROOT, Stage, now, read_json, sha256, write_json  # noqa: E402

QUEUE = LOOP / "render_queue.json"
WORK = LOOP / "work"


def substitute_pov(text: str, line: str) -> tuple[str, bool]:
    """Replace the paragraph under '### Producer POV' with `line`.

    Returns (text, changed). If the section is missing the text is returned
    untouched and `changed` is False — this never invents a section.
    """
    m = re.search(r"(### Producer POV\s*\n+)(\[HUMAN\]\s*)?(.+?)(\n\s*\n|\Z)",
                  text, re.S)
    if not m:
        return text, False
    if m.group(3).strip() == line.strip():
        return text, False
    return (text[:m.start()] + m.group(1) + "[HUMAN] " + line.strip() +
            (m.group(4) or "\n\n") + text[m.end():]), True


def main() -> None:
    with Stage("prepare",
               zero_work_hint="The queue held no usable row. Monday's draft "
                              "stage produced nothing.") as st:
        q = read_json(QUEUE, default=None)
        if q is None:
            st.named_stop("NO_QUEUE", "loop/render_queue.json does not exist",
                          unblock="Run: python loop/draft.py")
        # No approval gate. Topics were picked automatically under the hard
        # exclusion gate and POV lines came from her own bank, so there is
        # nothing here that requires her. The only human input this stage
        # honours is a DROP - an explicit override, applied if she used one.
        dropped = [i["slug"] for i in q["items"] if i.get("status") == "dropped"]
        if dropped:
            st.note(f"owner override dropped: {', '.join(dropped)}")

        WORK.mkdir(parents=True, exist_ok=True)
        prepared = []
        for it in q["items"]:
            if it.get("status") not in ("queued", "approved"):
                st.note(f"{it['slug']}: status={it.get('status')} — skipped")
                continue
            src = ROOT / it["script"]
            dst = ROOT / it["work_copy"]
            text = src.read_text()
            changed = False
            if it.get("pov_choice") == "bank" and it.get("pov_bank_line"):
                text, changed = substitute_pov(text, it["pov_bank_line"])
            dst.write_text(text)
            it["work_copy_sha256"] = sha256(dst)
            it["pov_substituted"] = changed
            it["prepared_at"] = now()
            prepared.append(it["slug"])
            st.work(f"froze {it['work_copy']}"
                    + (" (POV substituted from the bank)" if changed else ""))

        if not prepared:
            st.named_stop("NOTHING_TO_PREPARE",
                          "every row in the queue was dropped or is unusable",
                          detail={"statuses": [i.get("status")
                                               for i in q["items"]]})
        write_json(QUEUE, q)
        st.work(f"stamped {len(prepared)} row(s) into the queue")


if __name__ == "__main__":
    main()
