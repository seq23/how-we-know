#!/usr/bin/env python3
import argparse, json
from pathlib import Path
import soundfile as sf
from kokoro import KPipeline

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--script', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--voice', default='af_heart')
    ap.add_argument('--speed', type=float, default=0.98)
    args=ap.parse_args()
    text=Path(args.script).read_text().replace('[HUMAN]', '').strip()
    if not text: raise SystemExit('Script is empty')
    pipeline=KPipeline(lang_code='a')
    chunks=[]
    for _,_,audio in pipeline(text, voice=args.voice, speed=args.speed, split_pattern=r'\n+'):
        chunks.append(audio)
    if not chunks: raise SystemExit('No audio generated')
    import numpy as np
    merged=np.concatenate(chunks)
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    sf.write(args.output, merged, 24000)
    print(json.dumps({'output':args.output,'samples':len(merged),'sampleRate':24000}))
if __name__=='__main__': main()
