#!/usr/bin/env python3
import argparse
from pathlib import Path
import numpy as np
import soundfile as sf
from kokoro import KPipeline


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--script', default='production/audition/audition-script.txt')
    ap.add_argument('--output-dir', default='production/audition/generated')
    ap.add_argument('--voice', default='af_heart')
    ap.add_argument('--speeds', default='0.94,0.98,1.02')
    args = ap.parse_args()

    text = Path(args.script).read_text(encoding='utf-8').strip()
    if not text:
        raise SystemExit('Audition script is empty')

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pipeline = KPipeline(lang_code='a')

    for raw_speed in args.speeds.split(','):
        speed = float(raw_speed.strip())
        chunks = [audio for _, _, audio in pipeline(
            text,
            voice=args.voice,
            speed=speed,
            split_pattern=r'\n+',
        )]
        if not chunks:
            raise SystemExit(f'No audio generated for speed {speed}')
        merged = np.concatenate(chunks)
        output = out_dir / f'{args.voice}-speed-{speed:.2f}.wav'
        sf.write(output, merged, 24000)
        print(output)


if __name__ == '__main__':
    main()
