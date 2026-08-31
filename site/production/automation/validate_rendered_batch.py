#!/usr/bin/env python3
import argparse
import json
import subprocess
from pathlib import Path


def probe(path: Path) -> dict:
    proc = subprocess.run([
        'ffprobe', '-v', 'error', '-show_entries',
        'format=duration,size:stream=codec_type,codec_name,width,height,sample_rate',
        '-of', 'json', str(path),
    ], check=True, capture_output=True, text=True)
    return json.loads(proc.stdout)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--count', type=int, default=20)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[2]
    wavs = sorted((root / 'production/audio/narration').glob('*.wav'))[:args.count]
    videos = sorted((root / 'production/outputs').glob('*.mp4'))[:args.count]
    if len(wavs) != args.count or len(videos) != args.count:
        raise SystemExit(f'Expected {args.count} WAVs and MP4s; found {len(wavs)} and {len(videos)}')
    receipts = []
    for wav, video in zip(wavs, videos, strict=True):
        w = probe(wav)
        v = probe(video)
        duration = float(v['format']['duration'])
        if duration < 420:
            raise SystemExit(f'{video.name} is under 7 minutes: {duration:.1f}s')
        if int(v['format']['size']) < 1_000_000:
            raise SystemExit(f'{video.name} is suspiciously small')
        receipts.append({'wav': wav.name, 'video': video.name, 'durationSeconds': round(duration, 2)})
    receipt_path = root / 'production/outputs/render-receipt.json'
    receipt_path.write_text(json.dumps(receipts, indent=2), encoding='utf-8')
    print(receipt_path)


if __name__ == '__main__':
    main()
