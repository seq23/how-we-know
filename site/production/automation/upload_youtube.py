#!/usr/bin/env python3
import argparse, json, os
from datetime import datetime, timezone
from pathlib import Path
UPLOAD_SCOPE='https://www.googleapis.com/auth/youtube.upload'

def load_credentials(token_json, client_secrets):
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    if token_json and Path(token_json).exists():
        return Credentials.from_authorized_user_info(json.loads(Path(token_json).read_text()),[UPLOAD_SCOPE])
    if all(os.getenv(k) for k in ('YOUTUBE_REFRESH_TOKEN','YOUTUBE_CLIENT_ID','YOUTUBE_CLIENT_SECRET')):
        return Credentials(token=None,refresh_token=os.environ['YOUTUBE_REFRESH_TOKEN'],token_uri='https://oauth2.googleapis.com/token',client_id=os.environ['YOUTUBE_CLIENT_ID'],client_secret=os.environ['YOUTUBE_CLIENT_SECRET'],scopes=[UPLOAD_SCOPE])
    if client_secrets and Path(client_secrets).exists():
        return InstalledAppFlow.from_client_secrets_file(client_secrets,[UPLOAD_SCOPE]).run_local_server(port=0,access_type='offline',prompt='consent')
    raise SystemExit('Publish mode requires a token JSON, OAuth environment variables, or --client-secrets.')

def validate_publish_at(value):
    if not value:return None
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:raise SystemExit('publishAt must include an offset or Z')
    if parsed.astimezone(timezone.utc)<=datetime.now(timezone.utc):raise SystemExit('publishAt must be in the future')
    return parsed.astimezone(timezone.utc).isoformat().replace('+00:00','Z')

def write_receipt(path,payload):
    if not path:return
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--metadata',required=True); ap.add_argument('--video',required=True); ap.add_argument('--thumbnail')
    ap.add_argument('--token-json',default=os.getenv('YOUTUBE_TOKEN_JSON')); ap.add_argument('--client-secrets',default=os.getenv('YOUTUBE_CLIENT_SECRETS'))
    ap.add_argument('--publish-at'); ap.add_argument('--receipt-output'); ap.add_argument('--publish',action='store_true')
    args=ap.parse_args(); meta=json.loads(Path(args.metadata).read_text()); video=Path(args.video); thumbnail=Path(args.thumbnail) if args.thumbnail else None
    if not video.exists():raise SystemExit(f'Missing video: {video}')
    if thumbnail and not thumbnail.exists():raise SystemExit(f'Missing thumbnail: {thumbnail}')
    publish_at=validate_publish_at(args.publish_at or meta.get('publishAt')); privacy='private' if publish_at else meta.get('privacyStatus','private')
    receipt={'mode':'publish' if args.publish else 'dry-run','video':str(video),'thumbnail':str(thumbnail) if thumbnail else None,'title':meta['title'],'articleSlug':meta.get('articleSlug'),'privacyStatus':privacy,'publishAt':publish_at,'videoId':None,'watchUrl':None,'createdAt':datetime.now(timezone.utc).isoformat().replace('+00:00','Z')}
    if not args.publish: write_receipt(args.receipt_output,receipt); print(json.dumps(receipt,indent=2)); return
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    youtube=build('youtube','v3',credentials=load_credentials(args.token_json,args.client_secrets))
    status={'privacyStatus':privacy,'selfDeclaredMadeForKids':False,'containsSyntheticMedia':True}
    if publish_at:status['publishAt']=publish_at
    body={'snippet':{'title':meta['title'],'description':meta['description'],'tags':meta['tags'],'categoryId':meta.get('categoryId','28'),'defaultLanguage':'en'},'status':status}
    request=youtube.videos().insert(part='snippet,status',body=body,media_body=MediaFileUpload(str(video),chunksize=8*1024*1024,resumable=True))
    response=None
    while response is None:
        progress,response=request.next_chunk()
        if progress:print(json.dumps({'progress':progress.progress()}))
    video_id=response['id']
    if thumbnail:youtube.thumbnails().set(videoId=video_id,media_body=MediaFileUpload(str(thumbnail),mimetype='image/png')).execute()
    receipt.update(videoId=video_id,watchUrl=f'https://www.youtube.com/watch?v={video_id}',providerResponse=response)
    write_receipt(args.receipt_output,receipt); print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
