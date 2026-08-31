#!/usr/bin/env python3
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[2]; FINAL=ROOT/'production/scripts/final'; PLAIN=ROOT/'production/scripts/plaintext'
REPAIR={
3:"The final description should also link the exact observation to the canonical article so viewers can inspect the source trail rather than depend on the headline alone.",
4:"That context is what turns a strong thumbnail into a trustworthy documentary opening.",
5:"This check also prevents a beautiful deck photograph from being treated as a faithful view of the animal's normal visual world.",
6:"The difference between our sensor and the predator's eye belongs in the explanation, not in a footnote.",
7:"A second correction belongs here too. Deeper water does not always mean larger teeth, larger eyes, or a more active predator. Some lineages reduce eyes, rely more on chemical or mechanical sensing, or conserve energy through stillness. Others occupy the seafloor and feed on material that arrives from above. The farther the chart descends, the more important it becomes to show the whole community rather than one selected face. That broader view is the real payoff: depth changes the available strategies, but it does not write a single direction of evolution.",
8:"The production queue should use that rule when it chooses the next subjects.",
9:"The answer can also change with context. A still photograph may make teeth dominant; video may make movement more unsettling; a life-history fact may create more discomfort than appearance. The episode should let those categories compete rather than forcing every animal onto one visual scale. That produces more varied sequels and avoids twenty versions of the same close-up-jaw story. It also keeps the first-person answer honest: my choice reflects what I react to, while the evidence explains what the animal actually does.",
10:"It is also the safer title language for future updates.",
17:"That sequence keeps the metaphor attached to evidence.",
18:"It also gives the viewer a clean mental model: pressure changes boiling conditions, chemistry changes the water, cooling reveals the minerals, and gradients make life possible.",
}

def wc(t):return len(re.findall(r"\b[\w’'-]+\b",t))
def ts(s):s=int(round(s));return f'{s//60:02d}:{s%60:02d}'
for seq,path in enumerate(sorted(FINAL.glob('[0-9][0-9]-*.md')),1):
 if seq not in REPAIR:continue
 text=path.read_text();marker='\n### What to notice in the edit\n';title='Final editorial note'
 if f'### {title}\n' in text:
  text=text.replace(f'### {title}\n\n',f'### {title}\n\n{REPAIR[seq]} ',1)
 else:text=text.replace(marker,f'\n### {title}\n\n{REPAIR[seq]}\n{marker}',1)
 narr=re.search(r'## Narration\n(.*?)(?=\n## Human fingerprint gate)',text,re.S).group(1);sections=[]
 for part in re.split(r'(?m)^### ',narr)[1:]:n,b=part.split('\n',1);sections.append((n.strip(),b.strip()))
 plain='\n\n'.join(b.replace('[HUMAN] ','') for _,b in sections).strip()+'\n';count=wc(plain);dur=count/145*60
 text=re.sub(r'\*\*Word count:\*\*\s*\d+',f'**Word count:** {count}',text);text=re.sub(r'\*\*Estimated narration:\*\*\s*[^\n]+',f'**Estimated narration:** {int(dur//60)}m {int(round(dur%60)):02d}s at 145 WPM',text)
 elapsed=0;ch=[]
 for n,b in sections:ch.append(f'- {ts(elapsed)} {n}');elapsed+=wc(b)/145*60
 text=re.sub(r'## Chapters\n\n.*?(?=\n## Sources)','## Chapters\n\n'+'\n'.join(ch)+'\n',text,flags=re.S);path.write_text(text);(PLAIN/path.with_suffix('.txt').name).write_text(plain)
 print(path.name,count)
