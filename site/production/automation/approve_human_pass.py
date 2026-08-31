#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

PLACEHOLDERS = ('REPLACE THIS', 'YOUR NAME', 'PENDING HUMAN')


def require_human_text(path: Path, label: str) -> str:
    if not path.exists():
        raise SystemExit(f'Missing {label}: {path}')
    text = path.read_text(encoding='utf-8').strip()
    if '[HUMAN]' not in text:
        raise SystemExit(f'{label} must contain at least one truthful [HUMAN] observation line.')
    for placeholder in PLACEHOLDERS:
        if placeholder in text:
            raise SystemExit(f'{label} still contains unresolved text: {placeholder}')
    return text


def main():
    ap = argparse.ArgumentParser(description='Record human editorial approval for one final narration script.')
    ap.add_argument('--sequence', type=int, required=True)
    ap.add_argument('--reviewer', required=True)
    args = ap.parse_args()
    reviewer = args.reviewer.strip()
    if not reviewer:
        raise SystemExit('Reviewer name is required.')

    root = Path(__file__).resolve().parents[2]
    ledger_path = root / 'production/human-pass/approval-ledger.json'
    ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
    row = next((record for record in ledger if int(record['sequence']) == args.sequence), None)
    if not row:
        raise SystemExit(f'Unknown sequence {args.sequence}')

    prefix = f'{args.sequence:02d}'
    script = root / row['scriptPath']
    final_markdown = root / f'production/scripts/final/{prefix}-{row["slug"]}.md'
    checklist = root / row['humanPassPath']

    plaintext = require_human_text(script, 'Final plaintext narration')
    markdown = require_human_text(final_markdown, 'Final Markdown script')
    checklist_text = checklist.read_text(encoding='utf-8') if checklist.exists() else ''

    if re.search(r'^\s*- \[ \]', checklist_text, flags=re.MULTILINE):
        raise SystemExit('Human-pass checklist still contains unchecked required items.')
    if '[HUMAN]' not in checklist_text:
        raise SystemExit('Human-pass record must contain the truthful [HUMAN] observation.')
    if 'REPLACE THIS' in checklist_text:
        raise SystemExit('Human-pass record still contains the observation placeholder.')
    if '## SOURCES' not in markdown.upper():
        raise SystemExit('Final Markdown script must retain its SOURCES section.')
    if len(plaintext.split()) < 900:
        raise SystemExit('Final plaintext narration is unexpectedly short for the approved long-form format.')

    digest = hashlib.sha256(script.read_bytes()).hexdigest()
    approved_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    row.update(
        status='approved',
        reviewer=reviewer,
        approvedAt=approved_at,
        scriptSha256=digest,
    )
    ledger_path.write_text(json.dumps(ledger, indent=2) + '\n', encoding='utf-8')

    status_line = '**Status:** APPROVED — HASH RECORDED'
    checklist_text = re.sub(r'^\*\*Status:\*\*.*$', status_line, checklist_text, count=1, flags=re.MULTILINE)
    approval_block = (
        '\n## Recorded approval\n\n'
        f'- Reviewer: {reviewer}\n'
        f'- Approved at: {approved_at}\n'
        f'- Plaintext SHA-256: `{digest}`\n'
    )
    checklist_text = re.sub(r'\n## Recorded approval\n.*\Z', '', checklist_text, flags=re.DOTALL).rstrip()
    checklist.write_text(checklist_text + approval_block, encoding='utf-8')

    print(json.dumps(row, indent=2))


if __name__ == '__main__':
    main()
