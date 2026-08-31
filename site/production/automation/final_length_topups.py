#!/usr/bin/env python3
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[2]; FINAL=ROOT/'production/scripts/final'; PLAIN=ROOT/'production/scripts/plaintext'
ADD={
3:("The final test", "If the species, condition, time, location, and observation effort are not available, the video must keep the conclusion narrow. Curiosity survives that restraint; credibility depends on it."),
4:("The line I will keep", "I can say the animal scares me. I cannot say it is hunting people, predicting disaster, or becoming more dangerous because the frame looks dramatic. That distinction is the episode's ethical center."),
5:("A simple edit check", "Pause every time the narrator says red, black, or invisible and ask whether the current shot uses natural ambient light or artificial illumination. If it uses white ROV light, the caption must say so. If depth is uncertain, do not use the shot as proof of a depth-specific camouflage claim. The audience should be able to see why the same animal changes appearance instead of being asked to trust a color fact that contradicts the screen."),
6:("The final visual test", "Place a transparent animal over three backgrounds: open blue water, black water under ROV light, and a high-contrast graphic grid. The animal's visibility changes each time. That is the point. Transparency is contextual, and a camera designed to expose faint structures can make successful camouflage look ineffective. The final edit should celebrate the structures revealed by the camera while explaining that a predator does not receive the same optimized image."),
7:("The retention payoff", "The deepest point on the chart should not contain the ugliest creature. It should contain the limit of confirmed fish and a transition to other forms of life. That reversal gives the viewer a genuine surprise while correcting the premise. The episode begins as a horror ladder and ends as a lesson in energy budgets, sampling bias, and physiological boundaries. The chart becomes more interesting when the expected monster is replaced by a question: which body plans can keep functioning as pressure rises and food becomes less predictable?"),
8:("The editorial rule for future additions", "A new creature enters this catalog only when it adds a habitat, ecological role, adaptation, or evidence method that the current set does not already explain. That rule prevents automation from producing twenty near-identical predator profiles. It also means microbes, scavengers, filter feeders, migrators, symbionts, and gelatinous animals must receive space beside the familiar thumbnail species. The catalog should become a better map of the ecosystem as it grows, not merely a longer list."),
9:("The final invitation", "Ask viewers for the creature that unsettles them and the exact feature responsible. That produces more useful responses than asking for the 'scariest' name alone. A comment about teeth leads to feeding mechanics. A comment about size leads to measurement. A comment about transparent tissue leads to camouflage. The audience helps choose sequels while the channel keeps the conversation grounded in biology."),
10:("Measurement beats myth", "That is the final rule."),
15:("The reliable hook", "The protected pressure sphere and the return journey are dramatic enough. We do not need an unstable headcount."),
17:("The final edit check", "Show the waving, the bacterial growth, and the feeding motion as separate evidence steps before using the farming shorthand."),
18:("The closing correction", "Do not use stock footage of smoke, fire, or lava to illustrate the plume. Those images teach combustion and open-air boiling, which are exactly the wrong mechanisms. Original mineral-particle animation is both safer for copyright and better science. The final shot should move from the hot jet into the cooler biological zone, making the boundary between geology and life visible."),
20:("Dark is not empty", "That is the image to leave behind."),
}

def wc(t): return len(re.findall(r"\b[\w’'-]+\b",t))
def ts(s): s=int(round(s)); return f'{s//60:02d}:{s%60:02d}'
for seq,path in enumerate(sorted(FINAL.glob('[0-9][0-9]-*.md')),1):
    if seq not in ADD: continue
    text=path.read_text(); title,body=ADD[seq]; marker='\n### What to notice in the edit\n'
    if f'### {title}\n' not in text: text=text.replace(marker,f'\n### {title}\n\n{body}\n{marker}',1)
    narr=re.search(r'## Narration\n(.*?)(?=\n## Human fingerprint gate)',text,re.S).group(1); sections=[]
    for part in re.split(r'(?m)^### ',narr)[1:]: n,b=part.split('\n',1);sections.append((n.strip(),b.strip()))
    plain='\n\n'.join(b.replace('[HUMAN] ','') for _,b in sections).strip()+'\n'; count=wc(plain); dur=count/145*60
    text=re.sub(r'\*\*Word count:\*\*\s*\d+',f'**Word count:** {count}',text)
    text=re.sub(r'\*\*Estimated narration:\*\*\s*[^\n]+',f'**Estimated narration:** {int(dur//60)}m {int(round(dur%60)):02d}s at 145 WPM',text)
    elapsed=0; chapters=[]
    for n,b in sections:chapters.append(f'- {ts(elapsed)} {n}');elapsed+=wc(b)/145*60
    text=re.sub(r'## Chapters\n\n.*?(?=\n## Sources)','## Chapters\n\n'+'\n'.join(chapters)+'\n',text,flags=re.S)
    path.write_text(text);(PLAIN/path.with_suffix('.txt').name).write_text(plain)
    print(path.name,count)
