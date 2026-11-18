"""Every push to a branch from CI rebases onto the moved branch and retries.
A bare `git push` after a commit fails whenever another lane pushed first
(p-n-p Daily Authority Cycle, 18 Nov 2026: "! [rejected] main -> main (fetch first)").
Exempt: force pushes to a lane's own branch, tag pushes, deletes."""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUSH = re.compile(r"(^|run:\s*|[;&|({!]\s*|\b(then|do|if|else|until|while)\s+)git\s+push\b")  # command position only
EXEMPT = re.compile(r"\s(-f|--force|--force-with-lease|--tags|--delete|-d)\b|refs/tags|origin\s+\"?v[0-9$]")
LOOP = re.compile(r"\b(for|while|until)\b[^\n]*;\s*do\b|\bdo\s*$", re.M)


def bare_pushes(name, text):
    lines, bad = text.split("\n"), []
    for i, line in enumerate(lines):
        t = line.strip()
        if not PUSH.search(t) or re.match(r"(#|echo\b|printf\b)", t) or EXEMPT.search(t):
            continue
        win = "\n".join(lines[max(0, i - 6): i + 7])
        if re.search(r"pull\s+--rebase|\brebase\b", win) and LOOP.search(win):
            continue
        bad.append(f"{name}:{i + 1}: {t}")
    return bad


fails = []
files = sorted((ROOT / ".github/workflows").glob("*.y*ml"))
if not files:
    fails.append("no workflow files found (the check saw nothing)")
for f in files:
    fails += [f"bare git push (no rebase/retry): {b}" for b in bare_pushes(f.name, f.read_text())]
# The check itself: the pre-fix search-console-daily shape is caught, the fix and exemptions pass.
if bare_pushes("name", "      - name: a bare git push fails\n"):
    fails.append("self-test: a step name was flagged")
if not bare_pushes("old", "          git commit -m x\n          git push\n"):
    fails.append("self-test: a bare push was not caught")
fixed = ('          for i in 1 2 3; do git pull --rebase --autostash -q origin "$GITHUB_REF_NAME" && git push origin '
         '"HEAD:$GITHUB_REF_NAME" && break; [ "$i" = 3 ] && exit 1; sleep $((i*10)); done\n          git push -f origin "$branch"\n')
if bare_pushes("new", fixed):
    fails.append("self-test: the retry loop or a force push to its own branch was flagged")
for x in fails:
    print("FAIL:", x)
print("workflow push retry:", "FAILED" if fails else f"ok ({len(files)} workflows)")
sys.exit(1 if fails else 0)
