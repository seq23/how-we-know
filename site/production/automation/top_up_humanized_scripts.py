#!/usr/bin/env python3
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[2]
FINAL=ROOT/'production/scripts/final'; PLAIN=ROOT/'production/scripts/plaintext'
TOP={
2:("The three-part answer", "The final answer should land in three parts. Mechanically, reduce vulnerable gas spaces. Chemically, maintain proteins and membranes that work under the local pressure. Ecologically, remain within the depth and temperature range the species is adapted to. Leaving out any one part creates the wrong picture: a water-filled bag with no biology, a chemistry lecture with no physical intuition, or an animal that can supposedly travel anywhere in the ocean."),
3:("What would change my mind", "I would treat the surfacing claim as stronger if standardized surveys showed the same identified species appearing shallower across multiple years and locations, while observation effort stayed comparable. I would also look for matching temperature, oxygen, prey, or current changes. Until that evidence exists, the script should resist turning scattered events into one cause. This is not refusing the climate question. It is defining the evidence that would let us answer it."),
4:("The thumbnail bargain", "The thumbnail can use the frightening face, but the first minute has to repay that choice with scale and context. That is the bargain. We are not pretending the image is boring; we are refusing to let the image carry a false threat claim. If the creature is tiny, say so. If the shot was made inches from the animal under artificial light, show that. The audience can enjoy the fear and still leave with a more accurate model."),
5:("The claim I will not make", "I will not say that red pigment always evolved for camouflage or that every red animal is invisible at the same depth. Pigment can have multiple functions, and light fields vary. The supported claim is narrower: because red wavelengths disappear quickly, red tissue can return little available light and appear dark in many deep settings. The species, depth, and behavior decide whether that physical advantage is biologically relevant."),
6:("A predator does not see like our camera", "Camouflage is measured against another animal's visual system, not a human watching a color-corrected screen. Predators may detect contrast, polarization, motion, or wavelengths our display does not reproduce. A body that looks obvious in a paused frame may be harder to detect while drifting. The script should therefore say 'reduces visibility' rather than 'becomes invisible.' That wording is both more accurate and more interesting because it keeps the predator in the story."),
7:("The deeper-is-worse illusion", "Depth videos also suffer from selection bias. Cameras linger on the unusual animal. Editors choose the sharpest teeth. Soft, slow, common organisms receive less attention because they are harder to identify and less likely to become a thumbnail. The internet then treats the selected images as a representative census. This episode should reveal that pipeline. The creepiness curve is partly biology, partly camera technology, and partly what humans choose to share."),
8:("How this becomes a series", "Each habitat in this episode should open a route into the catalog. Twilight migration leads to lanternfish and bioluminescence. The midnight zone leads to anglerfish and transparent animals. The seafloor leads to whale falls. Vents lead to black smokers and yeti crabs. Trenches lead to snailfish, dumbo octopuses, and Challenger Deep. The broad episode earns watch time by answering the big question, then distributes attention to the specific videos instead of ending as an isolated list."),
9:("The honest winner", "My answer can remain the anglerfish as long as the script clearly labels it personal. The scientific section then explains the features that produced the reaction. That combination is more human than pretending neutrality and more accurate than declaring a universal champion. It also gives the viewer permission to disagree, which is exactly what the comments should be used for: preference and curiosity, not correction of a fake objective ranking."),
10:("Why deepest known is the correct phrase", "The ocean has not been mapped at identical resolution everywhere, and measurements continue to improve. Challenger Deep is the deepest known point supported by current surveys, not a guarantee that no unmeasured depression could ever be refined. The word known protects the claim without weakening it. It tells the viewer that science is reporting the best evidence available, with room for better measurement."),
12:("One final wording rule", "Use 'ancient-looking' only as a description of our reaction, never as evidence that the animal stopped evolving."),
14:("One final wording rule", "Use 'measured specimen' whenever the 495-kilogram value appears."),
15:("The release gate", "Before publication, recheck the depth value, the source date, and any wording that implies a current record. Do not add a visitor total simply because it makes the title cleaner. The engineering narrative remains strong without it, and the episode will age better."),
16:("What the camera may miss", "Much of the later whale-fall community is small, slow, microbial, or inside sediment and bone. A dramatic ROV pass can overrepresent large scavengers and underrepresent the processes that last longest. Original diagrams and sourced microscopy stills may explain the later stages better than a montage of sharks. The edit should follow the ecology, not only the largest available footage."),
17:("The source hierarchy", "The behavior comes from direct observation. The feeding interpretation gains support from isotope and lipid evidence. Broader statements about the family come from comparing species. Keeping that hierarchy visible prevents the title's farming metaphor from becoming a stronger claim than the paper supports."),
18:("The word smoke", "The plume looks like smoke because minerals precipitate when hot fluid meets cold seawater. It is not combustion. That distinction belongs in the first explanation, not buried at the end. The same visual can then show chimney growth: dissolved material becomes particles, particles settle, and layers of mineral structure accumulate around the flow."),
19:("The next record", "A future deeper sighting would not make this episode worthless. The evidence framework would still hold: identify the depth method, distinguish film from capture, state the species confidence, and compare the result with the proposed biochemical boundary. The script is built to survive a new record because it explains how records are established, not only who currently holds one."),
20:("The scale of one dive", "A single dive crosses only a narrow path through a zone spanning thousands of meters. Conditions can change horizontally as well as vertically. Oxygen, currents, particles, and animal density vary. The episode should not let one beautiful expedition clip become the visual definition of the entire midnight zone. Use multiple documented settings or clearly label the footage as one observation."),
}

def wc(t): return len(re.findall(r"\b[\w’'-]+\b",t))
def ts(s): s=int(round(s)); return f'{s//60:02d}:{s%60:02d}'
for seq,path in enumerate(sorted(FINAL.glob('[0-9][0-9]-*.md')),1):
    if seq not in TOP: continue
    text=path.read_text(); title,body=TOP[seq]
    marker='\n### What to notice in the edit\n'
    if f'### {title}\n' not in text: text=text.replace(marker,f'\n### {title}\n\n{body}\n{marker}',1)
    narr=re.search(r'## Narration\n(.*?)(?=\n## Human fingerprint gate)',text,re.S).group(1)
    sections=[]
    for part in re.split(r'(?m)^### ',narr)[1:]:
        n,b=part.split('\n',1); sections.append((n.strip(),b.strip()))
    plain='\n\n'.join(b.replace('[HUMAN] ','') for _,b in sections).strip()+'\n'; count=wc(plain); dur=count/145*60
    text=re.sub(r'\*\*Word count:\*\*\s*\d+',f'**Word count:** {count}',text)
    text=re.sub(r'\*\*Estimated narration:\*\*\s*[^\n]+',f'**Estimated narration:** {int(dur//60)}m {int(round(dur%60)):02d}s at 145 WPM',text)
    elapsed=0; chapters=[]
    for n,b in sections: chapters.append(f'- {ts(elapsed)} {n}'); elapsed+=wc(b)/145*60
    text=re.sub(r'## Chapters\n\n.*?(?=\n## Sources)','## Chapters\n\n'+'\n'.join(chapters)+'\n',text,flags=re.S)
    path.write_text(text); (PLAIN/path.with_suffix('.txt').name).write_text(plain)
    print(path.name,count)
