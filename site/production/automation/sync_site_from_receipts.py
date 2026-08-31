#!/usr/bin/env python3
import argparse, json, re, subprocess
from pathlib import Path

def iso_duration(seconds):
    total=int(round(float(seconds))); h,total=divmod(total,3600); m,s=divmod(total,60)
    return 'PT'+(f'{h}H' if h else '')+(f'{m}M' if m else '')+(f'{s}S' if s or (not h and not m) else '')

def main():
    ap=argparse.ArgumentParser(description='Activate site video records only after manually confirming scheduled videos are public.')
    ap.add_argument('--confirm-public',action='store_true',required=True)
    args=ap.parse_args(); root=Path(__file__).resolve().parents[2]
    questions=json.loads((root/'content/questions.json').read_text()); qmap={q['slug']:q for q in questions}
    updated=[]
    for receipt_path in sorted((root/'production/provider-receipts/youtube').glob('*.json')):
        r=json.loads(receipt_path.read_text()); vid=r.get('videoId'); slug=r.get('articleSlug')
        if not vid or not slug or slug not in qmap:continue
        q=qmap[slug]; seq=int(re.match(r'(\d+)-',receipt_path.name).group(1)); base=receipt_path.stem
        meta=json.loads((root/f'production/metadata/{base}.json').read_text()); transcript=(root/f'production/scripts/plaintext/{base}.txt').read_text().strip()
        probe=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(root/f'production/outputs/{base}.mp4')],capture_output=True,text=True,check=True)
        q['video']={'status':'published','videoId':vid,'title':q['question'],'descriptionFirstLine':q['directAnswer'],'thumbnailUrl':f'https://i.ytimg.com/vi/{vid}/maxresdefault.jpg','uploadDate':(r.get('publishAt') or r['createdAt'])[:10],'duration':iso_duration(probe.stdout.strip()),'transcript':transcript,'chapters':meta.get('chapters',[])}
        updated.append({'sequence':seq,'slug':slug,'videoId':vid})
    (root/'content/questions.json').write_text(json.dumps(questions,indent=2)+'\n')
    print(json.dumps({'updated':updated,'count':len(updated)},indent=2))
if __name__=='__main__':main()
