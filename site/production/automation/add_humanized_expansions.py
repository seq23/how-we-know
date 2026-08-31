#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
FINAL = ROOT / 'production/scripts/final'
PLAIN = ROOT / 'production/scripts/plaintext'

EXTRA = {
1: (
"A better way to look at the body",
"""The fastest way to stop treating a deep-sea animal as a monster is to rebuild the scene around it. Start with the water, not the face. Ask whether the animal is drifting in open water, moving over mud, sitting near a vent, or crossing a trench wall. Then ask what light is available. A reflective side, a transparent tissue, a red body, and a light organ can all be forms of concealment, but they work in different light fields. Next ask how often food arrives. A large mouth can look excessive in a photograph while functioning as insurance in a habitat where the next meal is unpredictable. Finally, ask whether the image shows a living animal at depth or a specimen after capture. Delicate tissue can collapse, eyes can change position, and colors can look dramatically different under deck lights.

That sequence changes the emotional meaning of the image without making it less compelling. The animal still looks unfamiliar. It simply stops looking arbitrary. The barreleye's transparent shield becomes a protected viewing window. The anglerfish's lure becomes a way to shorten a costly chase. A gelatinous animal's softness becomes compatible with a body that contains little compressible gas. A giant mouth becomes a response to scarcity rather than proof of aggression. This is the channel's editorial rule for every creature episode: restore depth, scale, condition, and function before using the close-up. If those four pieces are missing, the image may be excellent entertainment, but it is weak evidence about how the animal normally looks or lives."""
),
2: (
"What pressure actually changes",
"""Pressure is not one problem with one solution. It changes gas volume, chemical reactions, protein shape, membrane behavior, buoyancy, and the engineering required to observe an animal. That is why a deep species cannot be summarized as simply 'strong enough' to resist the water. The animal's tissues are mostly water, but its cells still have to maintain working molecules and membranes. Pressure-adapted proteins and cellular chemistry function inside a narrow environmental range. A species that lives permanently at depth may be highly successful there and still be physiologically fragile during a rapid trip to the surface.

The comparison with a submersible helps because it exposes two opposite strategies. The vehicle protects a small pocket of surface pressure inside a rigid sphere. The animal generally does not preserve a human-like pocket of surface conditions. It lives in equilibrium with the water around it and adapts its chemistry accordingly. The vehicle needs walls. The animal needs compatible biology. Both can fail when moved outside their design range, but for different reasons. This also explains why researchers value pressure-retaining samplers. A specimen that reaches the deck alive but decompressed may no longer behave or even look as it did at depth. When we describe pressure survival, the honest answer includes the observation problem: many of the animals we want to study are altered by the act of bringing them to us."""
),
3: (
"From one sighting to a real trend",
"""A trend needs a denominator. Ten unusual sightings can mean very different things if ten cameras were operating before and ten thousand are operating now. More ROV dives, fishing effort, phones, social media accounts, beach patrols, and reporting networks can increase the number of recorded events even when animal behavior has not changed. Researchers would want comparable observation effort, consistent identification, location, season, time of day, depth, and animal condition. Without that structure, a collection of viral clips is a collection of anecdotes.

That does not mean every sighting should be dismissed. A stranded or injured deep resident can reveal local currents, temperature stress, disease, capture effects, or an unusual oceanographic event. The responsible move is to narrow the claim. Instead of saying 'deep-sea creatures are surfacing,' say exactly what was observed: one oarfish was found at a location on a date; one deepwater shark was caught above its common range; one mass stranding occurred after a storm. Specific language preserves the evidence and prevents the story from outrunning it. For this episode, the retention payoff is the audit itself. The viewer sees a frightening headline become a set of testable questions. Sometimes the final answer is normal migration. Sometimes it is injury. Sometimes it remains unknown. Unknown is not a weak ending when the alternative is a fabricated trend."""
),
4: (
"How the camera manufactures a predator",
"""A deep-sea image can remove every cue the brain uses to judge danger. There may be no horizon, no hand, no ruler, and no familiar object. The animal fills the frame. The lens is close. Hard ROV light creates sharp shadows. Teeth remain visible because they are pale and reflective. Slow movement can look deliberate when the real reason is low energy availability. A still frame freezes the exact moment a jaw opens and erases the minutes of uneventful drifting around it. The resulting picture is not fake, but it is selected and framed for maximum visual impact.

The human fear response then does the rest. Forward-facing eyes suggest attention. Exposed teeth suggest attack. A lure looks deceptive because we map human intention onto it. A body without a familiar outline looks diseased or unfinished. Those reactions are useful to acknowledge because pretending the animals are not frightening would sound dishonest. The editorial move is to separate the feeling from the ecological claim. I can say an anglerfish face unsettles me. I cannot turn that reaction into evidence that it poses a meaningful threat to people. The episode should repeatedly restore size and distance after each dramatic close-up. That visual reset is the correction. It lets the thumbnail earn the click while the video earns trust by showing what the thumbnail left out."""
),
5: (
"The color experiment the ocean performs",
"""Imagine lowering a row of colored cards through clear water. The cards do not carry their appearance with them. Their appearance depends on which wavelengths remain available to reflect. Red wavelengths are absorbed relatively quickly, so a red body loses the light that would make it look red. Under the blue-green light that penetrates deeper, that same body can appear dark. The animal has not changed pigment. The lighting environment has changed the information available to a viewer or predator.

This is why ROV footage needs interpretation. White lamps bring a broad spectrum into a place where it normally does not exist. A shrimp that looks scarlet on camera may look nearly black under ambient conditions. The light makes the footage useful for identification, but it can mislead the audience about camouflage. Depth is also not a single switch. Water clarity, particles, angle, weather, and local conditions affect light penetration. Red coloration can be useful in one depth range and irrelevant in another. Some animals combine pigment with transparency, counterillumination, reflective tissue, or behavior. The strongest version of this script does not claim that every red deep-sea animal evolved for exactly the same reason. It shows the physics, then asks whether the documented habitat and behavior fit the camouflage explanation for that species."""
),
6: (
"Why becoming invisible is incomplete",
"""Transparency sounds like a perfect solution until the body has to digest food, move muscles, carry pigments, protect a nervous system, and reproduce. Those structures interact with light. A transparent animal can still reveal its gut, eyes, eggs, or prey. That is why open-water camouflage often combines partial transparency with reflective surfaces, small size, vertical posture, counterillumination, or behavior. The goal is not literal invisibility from every angle. It is reducing contrast against the background seen by a particular predator.

The barreleye makes the distinction especially clear. Its transparent shield does not make the whole fish disappear. It lets the tubular eyes look upward through protected tissue and rotate as the animal changes its feeding position. Net-caught specimens once obscured that anatomy because the shield was damaged. Live ROV observations changed the interpretation. That history is a useful reminder for the entire channel: specimen photographs and live behavior answer different questions. A specimen can support anatomy and identification. A live observation can reveal posture, movement, orientation, and the function of structures that collapse after capture. The humanized version of this episode should let the audience feel that discovery. The strange feature is not simply displayed; the evidence changes the explanation."""
),
7: (
"Why the horror ladder is backwards",
"""The popular depth chart usually selects one memorable predator for each band and makes the body designs look progressively more extreme. That is a storytelling device, not a survey. Deeper zones contain predators, but they also contain gelatinous drifters, deposit feeders, scavengers, sea cucumbers, amphipods, worms, microbes, and fish whose bodies are less armored and less visually dramatic. Food often becomes scarcer with depth, so waiting, drifting, conserving energy, and using whatever arrives can matter more than speed or aggression.

The deepest confirmed fish record also complicates the horror ladder. Snailfish do not look like the final boss in a game. Their soft bodies, reduced ossification, and pressure-compatible chemistry are part of what lets them occupy trenches. Below the likely fish depth boundary, other animals continue. The biological story is not that life becomes more monstrous until nothing can survive. It is that different body plans reach different limits. The episode should use the familiar scary chart as bait, then dismantle it with a broader community. Each time a predator appears, follow it with a non-predatory or low-energy specialist from a similar depth. That structural contrast is the human judgment the automated list would miss."""
),
8: (
"A tour organized by habitat, not celebrity",
"""A useful inventory of deep-sea life starts by separating the water column from the seafloor. In open water, animals must manage a three-dimensional world with few places to hide. Lanternfish, jellies, siphonophores, squid, crustaceans, and many small migrators move through layers of light and darkness. On the bottom, the habitat changes again. Mud, rock, coral, vents, seeps, carcasses, and trench walls support different communities. A sea cucumber processing sediment and a dragonfish hunting in midwater are both deep-sea animals, but they solve almost unrelated problems.

Depth zones are useful labels, not sealed rooms. Animals migrate across boundaries. Food falls through them. Currents transport particles and larvae. A whale carcass can connect surface productivity to the abyss. Hydrothermal vents can support food webs based on chemical energy, while most of the deep ocean still depends ultimately on material produced above. Trench communities occupy steep, isolated basins rather than one continuous hadal plain. This is why a single creature list always feels incomplete. The correct mental model is a network of habitats connected vertically and horizontally.

For retention, the episode should follow one unit of energy. Begin with surface production, let a particle sink, let a migrator carry carbon downward, let a predator take the migrator, let remains reach the bottom, and then show scavengers and microbes using what is left. The audience meets creatures along a pathway instead of hearing a catalog. That pathway also creates natural links to the whale-fall, midnight-zone, vent, and deep-fish episodes."""
),
9: (
"My fear ranking is not a danger ranking",
"""The anglerfish remains my personal answer because the face combines an exposed mouth, needlelike teeth, a lure, and an extreme reproductive story. That is a statement about my reaction, not a scientific score. Someone else may choose a giant squid because scale and rarity leave more room for imagination. Another viewer may choose a giant isopod because it resembles a familiar animal enlarged beyond comfort. The point is to make the subjectivity visible instead of disguising it as fact.

A danger ranking would produce a very different result. Most iconic deep-sea animals live far from unprotected human contact. The environmental hazards of depth—pressure, cold, darkness, distance, and equipment failure—matter more to a diver or submersible crew. Even the dramatic teeth usually solve a feeding problem in a food-poor habitat. They help retain prey; they are not evidence of an animal searching for people. The video should therefore run two scoreboards in parallel: visual fear and realistic human danger. The fear score can be playful and first-person. The danger score must remain evidence-based. When those scores diverge, the audience gets the payoff: the creature that looks worst is often not the thing a human expedition should fear most."""
),
10: (
"What a depth number leaves out",
"""A single maximum-depth value sounds final, but the seafloor is irregular and the measurement is an estimate with uncertainty. Soundings depend on water-column conditions, instrument calibration, navigation, processing, and the exact path of the survey. Pressure-derived depth calculations require assumptions about seawater properties and gravity. Different methods can produce slightly different values without one team being careless. That is why the best modern estimate is reported with an uncertainty rather than as a perfectly exact floor.

The geography also matters. The Mariana Trench is a long tectonic feature. Challenger Deep is the deepest known depression within it, and it contains more than one basin. Saying 'the Mariana Trench is 10,935 meters deep everywhere' would be wrong. The deepest point is a local extreme. Most of the trench and most of the global seafloor are shallower. The video should visualize a profile rather than a flat hole. That makes the measurement challenge visible and prevents the familiar error of treating a trench as a vertical crack with one uniform bottom."""
),
11: (
"What the record changes",
"""The 6,957-meter observation mattered because it expanded the documented depth of octopus life by more than a kilometer. It also changed the estimated share of seafloor habitat potentially available to octopuses. But the camera recorded an animal, not its entire life history. It did not reveal where the eggs were laid, how long development took, what the individual had eaten, or whether the same species routinely occupies that depth. A record is the edge of confirmed observation, not the edge of biological possibility.

That distinction makes the footage more interesting. The dumbo octopus is not impressive because a narrator can attach a superlative. It is impressive because a soft-bodied cephalopod was functioning on a trench floor where observation is expensive and rare. The human point of view in this episode should be wonder disciplined by the frame: here is what the dive showed, here is what the paper inferred, and here is what remains unseen."""
),
12: (
"What a fossil resemblance can and cannot prove",
"""A modern animal can retain features that resemble ancient relatives while still evolving continuously. Genes change. Populations adapt. Environments shift. The phrase 'living fossil' compresses that history into a misleading image of an organism frozen in time. For the frilled shark, the safer claim is that its lineage has ancient roots and its body retains a combination of traits viewers find unfamiliar—not that the exact modern species has remained unchanged for a stated number of millions of years.

The feeding story needs the same restraint. Long jaws and backward-pointing teeth support hypotheses about gripping slippery prey. Stomach contents and anatomy add evidence. Direct observations of successful hunting are scarce. The video should label each layer: observed anatomy, documented diet evidence, and inferred behavior. That separation is more credible than animating one dramatic strike and narrating it as settled fact."""
),
13: (
"Why one flash can mean opposite things",
"""A light signal has no meaning outside behavior and context. A predator can use light to attract prey. Prey can use a flash to startle a predator or illuminate it for a larger hunter. An animal can match dim light from above to erase its silhouette. Members of the same species can use patterned signals to find one another. The chemical mechanism may be similar while the ecological function is completely different.

That is why the MBARI percentages need careful narration. They demonstrate how common light production was among animals observed in a large ROV dataset. They do not tell us that every animal glows, that every species was equally detectable, or that one function dominates. The humanized edit should return to the same original light animation and change only the surrounding scene. The audience sees that chemistry is the tool; behavior supplies the meaning."""
),
14: (
"The record belongs to a specimen, not a silhouette",
"""Te Papa's displayed specimen is useful precisely because it can be measured, re-examined, and compared with other material. Its reported mass and total length are real specimen values, but even they require context. The animal was frozen, thawed, unfolded, and preserved. Tentacles can contract or be damaged. Water and ice can affect mass. Total length, mantle length, and mass therefore answer different size questions.

Projected maxima are a separate category. Larger beaks recovered from sperm whale stomachs suggest that larger colossal squid exist, but the relationship between beak size and total body mass is not yet supported by a large sample of complete specimens. The video should never place a projected giant beside the measured specimen without a label. 'Measured,' 'estimated,' and 'possible' must look different on screen. That visual honesty lets the animal remain extraordinary without borrowing certainty from an incomplete record."""
),
15: (
"Why repeat dives matter more than a guest list",
"""A first descent proves that a vehicle can reach the target and return. Repeated descents allow mapping, sampling, comparison, calibration, and repair based on actual performance. They also expose the variability of the trench floor. One landing cannot describe an entire depression, much less the full Mariana Trench. A repeatable vehicle turns a historic event into a scientific program.

The cabin is only one part of that program. Navigation must work without GPS underwater. Acoustic systems, inertial instruments, pressure sensors, cameras, lights, batteries, thrusters, ballast, and communications each have failure modes. The depth estimate itself is calculated from measured pressure and environmental assumptions. The human story is not merely who sat in the sphere. It is the network of engineers, pilots, scientists, ship crew, and analysts required to make the observation defensible."""
),
16: (
"Why the phases overlap",
"""The familiar three-stage whale-fall diagram is a model, not a stopwatch. Mobile scavengers can arrive while soft tissue remains. Smaller organisms use enriched sediment before every large piece is gone. Microbial processes inside bone begin while other feeding continues. Current, oxygen, sediment, carcass size, and local species change the pace. A small carcass in one setting will not reproduce the timeline of a large whale in another.

The overlap matters because it turns the whale into more than a pile of calories. It changes local chemistry, creates hard structure on soft sediment, and can provide habitat over long periods. The edit should keep one timeline on screen while multiple processes appear together. That avoids the false impression that the ecosystem waits for a clean handoff between chapters. The final image should be the same skeleton at a later time, still functioning as habitat after the dramatic scavenger footage has ended."""
),
17: (
"What makes farming the cautious word",
"""The crab's repeated waving brings bacteria-covered setae into contact with flowing, chemically rich water. Stable-isotope and lipid evidence supports those bacteria as an important food source. The crab also scrapes material from the setae toward its mouth. Together, those observations make cultivation or farming a useful shorthand. But the word can imply planning and ownership that the evidence does not require.

The safer explanation is behavioral engineering. The crab creates conditions that favor a microbial food source and then harvests it. Related yeti crabs use different body surfaces and live in different vent or seep environments, so one species should not stand in for the whole family. The visual structure should move from behavior, to microbes, to chemical flow, to feeding evidence. That sequence shows why the interpretation is strong without pretending researchers watched the crab make a human-style agricultural decision."""
),
18: (
"Where the usable energy appears",
"""The hottest fluid is not the habitat most animals occupy. Life clusters where vent fluid mixes with cold seawater and creates gradients in temperature and chemistry. Microbes use reduced chemicals from the vent system to build organic matter. Larger organisms depend directly or indirectly on that microbial production. The energy story therefore sits at the boundary, not inside the hottest jet.

Black smokers also change with time. Flow paths clog or shift. Chimneys grow, break, and become inactive. A vent field can contain hot focused flow, diffuse seepage, and older mineral structures at once. The video should avoid one perfect chimney standing in for every vent. Use the cutaway to show circulation through cracks, then return to the seafloor and show multiple mixing zones. This makes the non-boiling water part of a larger system rather than a single physics trick."""
),
19: (
"Why the boundary is biochemical, not a wall",
"""Researchers connect the apparent fish depth limit to cellular chemistry, including the balance of compounds that help proteins function under pressure. As depth increases, the required biochemical adjustments approach constraints imposed by the animal's body fluids. That creates a predicted range rather than a sharp line painted across every trench. Temperature, species history, food, and local conditions can still influence where fish are observed.

The kilometer below the deepest confirmed fish is therefore not empty. Amphipods, microbes, and other pressure-adapted organisms continue into deeper hadal water. The record tells us something specific about bony fish, not life as a whole. The edit should show the filmed fish, the captured specimens, the predicted range, and Challenger Deep on the same depth scale. The unused space below the fish becomes the final open question instead of a claim that nothing lives there."""
),
20: (
"How the zone connects the surface and abyss",
"""The midnight zone is not isolated from the sunlit ocean even though sunlight does not reach it. Sinking particles carry carbon downward. Migrating animals feed near the surface and return to depth. Predators intercept that movement. Carcasses and waste continue toward the bottom. The zone is therefore dark but energetically connected to processes above.

Its enormous volume also makes observation deceptive. An ROV or submersible illuminates a tiny moving window. Animals can avoid the light, approach it, or remain beyond camera range. Nets sample different organisms and can damage delicate bodies. Acoustic instruments detect broader patterns but cannot always identify species. A complete picture requires those methods together. The humanized episode should make the machinery visible for a moment so the viewer understands why a habitat containing so much water can still be described from relatively narrow observations."""
),
}


def count_words(text):
    return len(re.findall(r"\b[\w’'-]+\b", text))


def timestamp(seconds):
    seconds = int(round(seconds))
    return f"{seconds//60:02d}:{seconds%60:02d}"


def main():
    rows=[]
    for seq, path in enumerate(sorted(FINAL.glob('[0-9][0-9]-*.md')),1):
        text=path.read_text()
        title, body=EXTRA[seq]
        marker='\n### What to notice in the edit\n'
        if marker not in text:
            raise SystemExit(f'missing insertion marker: {path}')
        if f'### {title}\n' not in text:
            text=text.replace(marker, f'\n### {title}\n\n{body}\n{marker}',1)
        # Rebuild word count, duration, chapters, plaintext
        narr=re.search(r'## Narration\n(.*?)(?=\n## Human fingerprint gate)',text,re.S).group(1)
        parts=re.split(r'(?m)^### ',narr)
        sections=[]
        for part in parts[1:]:
            name, section_body=part.split('\n',1)
            sections.append((name.strip(),section_body.strip()))
        plain='\n\n'.join(section_body.replace('[HUMAN] ','') for _,section_body in sections).strip()+'\n'
        wc=count_words(plain)
        duration=wc/145*60
        text=re.sub(r'\*\*Word count:\*\*\s*\d+',f'**Word count:** {wc}',text)
        text=re.sub(r'\*\*Estimated narration:\*\*\s*[^\n]+',f'**Estimated narration:** {int(duration//60)}m {int(round(duration%60)):02d}s at 145 WPM',text)
        chapter_lines=[]; elapsed=0
        for name,section_body in sections:
            chapter_lines.append(f'- {timestamp(elapsed)} {name}')
            elapsed += count_words(section_body)/145*60
        text=re.sub(r'## Chapters\n\n.*?(?=\n## Sources)', '## Chapters\n\n'+'\n'.join(chapter_lines)+'\n', text, flags=re.S)
        path.write_text(text)
        (PLAIN/path.with_suffix('.txt').name).write_text(plain)
        rows.append((path.name,wc,duration))
    for name,wc,d in rows:
        print(f'{name}: {wc} words / {d/60:.1f} min')

if __name__=='__main__':
    main()
