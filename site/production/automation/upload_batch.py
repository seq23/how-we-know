#!/usr/bin/env python3
import argparse, json, subprocess
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

def parse_times(value):
    values=[]
    for token in value.split(','):
        h,m=map(int,token.strip().split(':')); values.append((h,m))
    return values

def main():
    ap=argparse.ArgumentParser(description='Dry-run or upload a long-form YouTube launch batch. Dry run is default.')
    ap.add_argument('--start-date',required=True,help='YYYY-MM-DD in the selected timezone')
    ap.add_argument('--timezone',default='America/Chicago')
    ap.add_argument('--daily-times',default='09:00,12:30,16:00,19:30')
    ap.add_argument('--limit',type=int,default=20); ap.add_argument('--publish',action='store_true')
    args=ap.parse_args(); tz=ZoneInfo(args.timezone); start=date.fromisoformat(args.start_date); times=parse_times(args.daily_times)
    root=Path(__file__).resolve().parents[2]; queue=json.loads((root/'production/video-queue.json').read_text())[:args.limit]
    receipts=root/'production/provider-receipts/youtube'; receipts.mkdir(parents=True,exist_ok=True)
    for offset,item in enumerate(queue):
        sequence=int(item['sequence']); slug=item.get('slug') or item['articleSlug']; base=f'{sequence:02d}-{slug}'
        day=start+timedelta(days=offset//len(times)); hour,minute=times[offset%len(times)]
        publish_at=datetime(day.year,day.month,day.day,hour,minute,tzinfo=tz).isoformat()
        cmd=['python',str(root/'production/automation/upload_youtube.py'),'--metadata',str(root/f'production/metadata/{base}.json'),'--video',str(root/f'production/outputs/{base}.mp4'),'--thumbnail',str(root/f'production/thumbnails/png/{base}.png'),'--publish-at',publish_at,'--receipt-output',str(receipts/f'{base}.json')]
        if args.publish:cmd.append('--publish')
        subprocess.run(cmd,check=True)
if __name__=='__main__':main()
