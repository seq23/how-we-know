#!/usr/bin/env node
import fs from 'node:fs';
const [,,slug,videoId,thumbnailUrl,uploadDate,duration]=process.argv;
if(!slug||!videoId||!thumbnailUrl||!uploadDate||!duration){console.error('usage: sync_published_video.mjs SLUG VIDEO_ID THUMBNAIL_URL YYYY-MM-DD PT#M#S');process.exit(2)}
const p=new URL('../../content/questions.json',import.meta.url); const qs=JSON.parse(fs.readFileSync(p,'utf8'));
const q=qs.find(x=>x.slug===slug); if(!q) throw new Error(`Unknown slug: ${slug}`);
const meta=JSON.parse(fs.readFileSync(new URL(`../metadata/${String(qs.indexOf(q)+1).padStart(2,'0')}-${slug}.json`,import.meta.url),'utf8'));
q.video={status:'published',videoId,title:meta.title,descriptionFirstLine:meta.descriptionFirstLine,thumbnailUrl,uploadDate,duration,transcript:fs.readFileSync(new URL(`../scripts/plaintext/${String(qs.indexOf(q)+1).padStart(2,'0')}-${slug}.txt`,import.meta.url),'utf8').trim(),chapters:meta.chapters};
fs.writeFileSync(p,JSON.stringify(qs,null,2)+'\n'); console.log(JSON.stringify({slug,videoId,status:'published'}));
