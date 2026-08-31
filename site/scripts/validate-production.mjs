import fs from 'node:fs'; import path from 'node:path';
const root=process.cwd(); const qs=JSON.parse(fs.readFileSync(path.join(root,'content/questions.json'),'utf8'));
const idx=JSON.parse(fs.readFileSync(path.join(root,'production/scripts/index.json'),'utf8'));
if(idx.length!==qs.length) throw new Error(`script index ${idx.length} != questions ${qs.length}`);
for(let i=0;i<qs.length;i++){
 const n=String(i+1).padStart(2,'0'), slug=qs[i].slug;
 const required=[`production/scripts/final/${n}-${slug}.md`,`production/scripts/plaintext/${n}-${slug}.txt`,`production/metadata/${n}-${slug}.json`,`production/thumbnails/svg/${n}-${slug}.svg`,`production/thumbnails/png/${n}-${slug}.png`,`production/packages/${n}-${slug}/scene-plan.json`];
 for(const rel of required) if(!fs.existsSync(path.join(root,rel))) throw new Error(`missing ${rel}`);
 const text=fs.readFileSync(path.join(root,required[1]),'utf8').trim(); const wc=(text.match(/\b[\w’'-]+\b/g)||[]).length;
 if(wc<900) throw new Error(`${slug} script too short: ${wc}`);
 const meta=JSON.parse(fs.readFileSync(path.join(root,required[2]),'utf8'));
 if(meta.title!==qs[i].question) throw new Error(`${slug} title drift`);
 if(meta.descriptionFirstLine!==qs[i].directAnswer) throw new Error(`${slug} direct-answer drift`);
}
const rights=JSON.parse(fs.readFileSync(path.join(root,'production/asset-rights-manifest.json'),'utf8'));
for(const a of rights){ if(a.assetStatus==='approved' && a.commercialUseAllowed!==true) throw new Error(`admitted asset not commercially cleared: ${a.assetId}`); }
console.log(JSON.stringify({questions:qs.length,scripts:idx.length,rightsAssets:rights.length,status:'pass'}));
