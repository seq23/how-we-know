#!/usr/bin/env python3
import argparse, hashlib, json
from pathlib import Path

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--count',type=int,default=20)
    args=ap.parse_args()
    root=Path(__file__).resolve().parents[2]
    ledger=json.loads((root/'production/human-pass/approval-ledger.json').read_text(encoding='utf-8'))[:args.count]
    if len(ledger)!=args.count: raise SystemExit(f'Expected {args.count} human-pass records; found {len(ledger)}')
    failures=[]
    for row in ledger:
        script=root/row['scriptPath']
        actual=hashlib.sha256(script.read_bytes()).hexdigest() if script.exists() else None
        if row.get('status')!='approved': failures.append(f"{row['sequence']:02d} not approved")
        elif not row.get('reviewer'): failures.append(f"{row['sequence']:02d} missing reviewer")
        elif actual!=row.get('scriptSha256'): failures.append(f"{row['sequence']:02d} script changed after approval")
    if failures: raise SystemExit('Human-pass gate failed:\n- '+'\n- '.join(failures))
    print(json.dumps({'approved':args.count,'status':'pass'},indent=2))
if __name__=='__main__': main()
