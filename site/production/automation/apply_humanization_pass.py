#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FINAL = ROOT / 'production/scripts/final'
PLAIN = ROOT / 'production/scripts/plaintext'
HUMAN = ROOT / 'production/human-pass'
INDEX = ROOT / 'production/scripts/index.json'
AUDIT_JSON = ROOT / 'production/research/number-verification.json'
AUDIT_MD = ROOT / 'production/research/number-verification.md'

DATA = {
1: {
'opening': "That fish is not deformed. The photograph is what happens when an animal built for darkness meets our daylight, our camera angle, and our idea of what a normal body should look like. The useful question is not why deep-sea creatures are weird. It is what problem each feature solves.",
'pov': "[HUMAN] I used to look at deep-sea animals as a collection of freaks. The source material changed that. Once I matched each feature to a constraint—darkness, pressure, cold, scarce food—the transparent head and oversized mouth stopped looking random and started looking precise.",
'structure_title': "Four problems, four body plans",
'structure': "This episode works as a problem-solution montage rather than a parade of creatures. First, darkness rewards eyes that collect faint light, bodies that erase their outline, and light organs that communicate without sunlight. Second, scarce food rewards jaws and stomachs that can use a rare opportunity. Third, high pressure punishes large gas spaces and favors water-rich bodies. Fourth, cold and low food supply reward slow, efficient movement. None of those rules produces one standard deep-sea shape. They produce many different answers. A barreleye, anglerfish, siphonophore, sea cucumber, and deep octopus can occupy the same broad world while solving different versions of the same problem.",
'visual': "The visual test for this episode is simple: never show a close-up without restoring context. Put the depth on screen. Show the animal's approximate size when the source provides it. Distinguish a live ROV observation from a specimen damaged by nets or decompression. The goal is not to make the creature less interesting. It is to stop the camera from manufacturing the weirdness we then pretend to explain.",
'boundary': "There is no single adaptation called a deep-sea body plan, and 'weird' is not a scientific category. NOAA describes the deep ocean as dark, cold, food-poor, and high-pressure, but species occupy different depths and habitats. A feature that helps in open midwater may be useless on the seafloor. A live animal may also look very different from a preserved specimen. The script can explain documented functions and plausible tradeoffs; it cannot claim that every unusual feature evolved for one reason.",
'closing': "The deep sea does not manufacture monsters. It manufactures specialists. The next time a creature looks impossible, ask what light reaches it, how often it eats, whether it carries gas, and what the camera has done to its scale. That answer is usually more surprising than the word weird.",
'variation': 'Problem-solution montage with scale restoration; no ranked creature list.',
'claims': [
('Pressure increases by about one atmosphere per 10 meters of seawater.', 'https://oceanexplorer.noaa.gov/ocean-fact/animal-pressure/', 'verified', 'NOAA states the approximate relationship and gives 100 m as about 10 atmospheres.'),
('Sunlight is absent below roughly 200 meters in the simplified NOAA deep-ocean explainer.', 'https://oceanexplorer.noaa.gov/explainers/marine-life/', 'verified-with-context', 'Light penetration varies with conditions; the script uses the value as a broad zone boundary, not an exact switch.'),
('Average deep-ocean temperature is about 4°C in NOAA educational summaries.', 'https://oceanexplorer.noaa.gov/ocean-fact/deep-ocean/', 'verified-with-context', 'Local temperatures vary, especially near vents.')]
},
2: {
'opening': "At 2,000 meters, the surrounding pressure is about 200 atmospheres. The surprising part is not that deep-sea animals have stronger armor. It is that many avoid the most crushable feature in the first place: a large pocket of gas.",
'pov': "[HUMAN] The correction I had to make in my own head was simple: deep-sea animals are not spending their lives holding back an ocean that wants to flatten them. Most are water-rich and live with their internal pressure close to the water around them.",
'structure_title': "The balloon test",
'structure': "Picture two objects descending together: a sealed balloon and a water-filled bag. The balloon changes dramatically because gas compresses. The water-filled bag changes much less. That is not a complete model of an animal, but it explains why lungs and gas-filled swim bladders are such important pressure problems. Deep species still need proteins, membranes, enzymes, and nervous systems that function under high pressure. They are not immune. They are adapted to a pressure regime. Bring some of them to the surface too quickly and the chemistry, temperature, and tissues can fail even when there is no dramatic crushing event.",
'visual': "The edit should alternate between the pressure scale and examples of body design: a human lung, a gas bladder, a water-rich gelatinous animal, and a rigid submersible pressure sphere. That contrast keeps the explanation physical. It also prevents the common mistake of using a dramatic implosion animation as if every deep animal were an air-filled machine.",
'boundary': "The phrase 'water is incompressible' is a useful simplification, not a claim that pressure has no biological effect. NOAA notes that pressure changes chemical reaction rates and that pressure-adapted animals can develop metabolic problems at the surface. Some vertical migrants also tolerate large daily pressure changes, but that does not mean every permanent deep resident can move freely between the surface and the abyss.",
'closing': "Deep-sea animals survive pressure by being built for it from the molecule up, not by wearing invisible armor. The cleanest clue is what they do not carry: large gas spaces that would behave very differently as the water above them gets heavier.",
'variation': 'Myth-first physics thought experiment using a balloon and water-filled bag.',
'claims': [
('Ocean pressure increases about one atmosphere for every 10 meters.', 'https://oceanexplorer.noaa.gov/ocean-fact/animal-pressure/', 'verified', 'NOAA educational approximation.'),
('Pressure at 2,000 meters is approximately 200 atmospheres.', 'https://oceanexplorer.noaa.gov/ocean-fact/animal-pressure/', 'verified', 'Explicit NOAA example.'),
('Some migrating species experience a pressure range of about 100 atmospheres.', 'https://oceanexplorer.noaa.gov/ocean-fact/animal-pressure/', 'verified-with-context', 'NOAA says some species; do not generalize to all deep-sea animals.')]
},
3: {
'opening': "A strange fish near the surface is not proof that the deep sea is sending a warning. Before the story becomes climate collapse, earthquake prediction, or an omen, there is a more basic question: was this animal actually out of place?",
'pov': "[HUMAN] I understand why one unusual animal feels like a signal. I also know how quickly I can turn one image into a trend when I have not checked the species, time of day, current, condition, or previous records.",
'structure_title': "How I would audit the viral clip",
'structure': "Start with identity. 'Deep-sea creature' is too broad to be useful. Then check the animal's known depth range and whether it was alive, injured, caught, stranded, or simply photographed during normal movement. Next check the clock. Billions of animals participate in diel vertical migration, moving upward in darkness to feed and returning before daylight. Then check location, currents, storms, temperature, oxygen, and capture method. Finally, ask whether similar observations were collected with comparable effort. A single event can be real and important without proving a global trend.",
'visual': "This episode should look like an evidence audit, not a monster reveal. Freeze the viral-style frame, then add one layer at a time: species name, normal depth, time, condition, location, and comparison data. The open loop is whether the animal is a normal migrant, an injured deep resident, or a genuinely unusual observation. The answer may remain uncertain, and that is acceptable.",
'boundary': "Diel vertical migration explains enormous routine movement in the water column, but it does not explain every deep animal found at the surface. A permanent deep resident may arrive because of injury, currents, capture, disease, or another local event. One observation cannot establish that deep-sea creatures as a group are surfacing more often. That claim requires repeated, standardized observations over time.",
'closing': "One strange sighting is a clue, not a diagnosis. The responsible story begins with species, condition, time, place, and previous records. If those pieces are missing, the honest headline is not 'the deep sea is changing.' It is 'we do not yet know why this animal was here.'",
'variation': 'Viral-claim audit built around six evidence checks.',
'claims': [
('Billions of animals participate in daily vertical migration.', 'https://oceanexplorer.noaa.gov/ocean-fact/vertical-migration/', 'verified', 'NOAA describes billions and billions of animals moving daily.'),
('Light is a primary cue for diel vertical migration, with temperature, prey, and predation risk also influencing it.', 'https://oceanexplorer.noaa.gov/ocean-fact/vertical-migration/', 'verified', 'NOAA lists these factors.'),
('Many migrators move upward at night and return to depth before sunrise.', 'https://oceanexplorer.noaa.gov/ocean-fact/vertical-migration/', 'verified-with-context', 'Applies to many migrators, not every midwater species.')]
},
4: {
'opening': "The thing most likely to kill a human at a thousand meters is not a fish. It is the environment. Teeth, glowing lures, and black water trigger fear instantly, but pressure, cold, distance, and equipment failure are the real hazards.",
'pov': "[HUMAN] The close-up teeth still work on me. Then I check the scale, and the 'monster' is often a small fish using the only feeding equipment that makes sense where a missed meal can matter.",
'structure_title': "The fear test",
'structure': "For every frightening image, run four checks. First: size. Is the animal centimeters long or meters long? Second: distance. Was the camera inches from the mouth? Third: behavior. Is the animal attacking, feeding, drifting, or simply facing the lens? Fourth: actual human exposure. Most iconic deep-sea animals do not share ordinary human space at all. Anglerfish lures, dragonfish teeth, and giant squid size are real biological features. The leap from unsettling anatomy to human danger is usually ours.",
'visual': "Open with a tight crop, then pull back to reveal scale. Repeat the technique with teeth, eyes, and bioluminescent lures. This structure lets the viewer feel the fear before the episode explains it. The final reveal should be a submersible or pressure diagram, shifting the threat from the creature to the environment without pretending the animal is harmless to its own prey.",
'boundary': "'Scary' is subjective, and a close-up can remove the information needed to judge danger. Some deep predators are genuinely large, and many are dangerous to prey. That is different from posing a routine threat to humans. The script should not claim that no deep-sea animal could ever injure a person; it should say that pressure, cold, darkness, distance, and machinery dominate the practical risk of deep-ocean exploration.",
'closing': "The deep sea is dangerous, but the horror face is usually a distraction. Restore scale, behavior, and distance, and the creature becomes an animal again. The black water, crushing pressure, and long route home are what should make the human nervous.",
'variation': 'Fear-response cold open followed by four-part danger audit and scale pullbacks.',
'claims': [
('The deep ocean generally begins around 200 meters in NOAA educational definitions.', 'https://oceanexplorer.noaa.gov/ocean-fact/deep-ocean/', 'verified-with-context', 'A broad educational boundary, not a universal ecological cutoff.'),
('Below 1,000 meters, sunlight is absent in NOAA’s simplified zone description.', 'https://oceanexplorer.noaa.gov/ocean-fact/deep-ocean/', 'verified-with-context', 'Water clarity and definitions vary; use as a zone-scale statement.'),
('Deep-ocean temperature averages about 4°C in the NOAA explainer.', 'https://oceanexplorer.noaa.gov/ocean-fact/deep-ocean/', 'verified-with-context', 'Local conditions vary.')]
},
5: {
'opening': "A red shrimp can look almost black in the water where it lives. Bring in white ROV lights and the same animal suddenly turns bright red. The color did not change. The available light did.",
'pov': "[HUMAN] What surprised me is that red is not a warning color down there. Under the light that actually reaches the animal, red can function more like black camouflage.",
'structure_title': "Turn off the red light",
'structure': "Color is reflected light. At the surface, a red body reflects red wavelengths to our eyes. As those wavelengths are absorbed by seawater, there is less red light available to reflect. NOAA's educational page says red light does not penetrate at about 100 meters, while blue travels much farther. That makes red and black useful midwater colors. The dramatic red animals in expedition footage are often being illuminated by white lamps that restore wavelengths absent from their normal world.",
'visual': "Treat the episode like a lighting experiment. Show the same original illustration under full-spectrum light, then remove red wavelengths and let the body darken. Follow with an ROV-light reveal. Do not use unlicensed expedition footage simply because it demonstrates the effect well; the original diagram and admitted media must carry the explanation unless an external clip passes the rights manifest.",
'boundary': "The depth at which a color disappears varies with water clarity, particles, sun angle, and the amount of light. 'Red disappears at 100 meters' is an educational approximation, not a universal hard line. Red coloration is also not used by every deep animal and does not make an animal perfectly invisible. Bioluminescent predators, close-range vision, silhouette, movement, and other senses still matter.",
'closing': "Red deep-sea animals are not dressed for our lights. They are dressed for the wavelengths their world removes. The next time an ROV reveals a brilliant scarlet squid or shrimp, remember that the camera brought the red light with it.",
'variation': 'Visual light-removal experiment instead of a creature profile.',
'claims': [
('Red light is rapidly filtered as depth increases and effectively does not reach the deep ocean.', 'https://oceanexplorer.noaa.gov/ocean-fact/red-color/', 'verified', 'NOAA explanation.'),
('NOAA states that at about 100 meters red light no longer penetrates in its educational example.', 'https://oceanexplorer.noaa.gov/ocean-fact/red-color/', 'verified-with-context', 'The page also notes that actual penetration varies by conditions.'),
('Red animals can appear blackish at depth because there is no red light to reflect.', 'https://oceanexplorer.noaa.gov/ocean-fact/red-color/', 'verified', 'Core mechanism stated by NOAA.')]
},
6: {
'opening': "Transparency does not make an animal disappear. It makes the edges harder to find. In open water, where there is no rock, plant, or burrow to hide behind, losing an outline can be the difference between being seen and being missed.",
'pov': "[HUMAN] The barreleye is the image I keep coming back to because the transparent part is not a science-fiction glass skull. It is a fragile, fluid-filled shield around eyes that can rotate.",
'structure_title': "What can be transparent—and what cannot",
'structure': "A body is not one optical material. Gelatinous tissue can transmit light well, but pigment, food, eyes, muscles, and internal organs are harder to hide. That is why many transparent animals still have visible guts or eyes. Some solve the problem with mirrors, pigment, narrow body shapes, or positioning. The barreleye is an important correction: its shield is transparent, but the whole fish is not. MBARI's live ROV observations showed that the tubular eyes rotate inside that shield, a feature that preserved specimens had failed to reveal.",
'visual': "Use an anatomy case study rather than a general list. Begin with a silhouette, reveal the transparent tissue, then isolate the structures that still scatter or absorb light. For the barreleye, rely on an original diagram unless a licensed clip is admitted; MBARI's reporting supports the facts, but the site's copyright notice means its images and footage are not automatically commercial-use assets.",
'boundary': "Transparency is not perfect invisibility. It works best in open water and against certain viewing angles and light conditions. It can be costly because tissues still need structure and protection. The barreleye's transparent shield should not be generalized to all barreleyes or all transparent animals without species-specific evidence. MBARI's feeding scenario around siphonophores is presented as a working hypothesis, not direct proof of every meal.",
'closing': "The deep ocean does not need an invisibility cloak. Sometimes it only needs a body that gives the predator less to lock onto. Transparency is not nothing. It is a carefully managed compromise between being alive and being hard to see.",
'variation': 'Single-animal anatomy case study with an optical-material breakdown.',
'claims': [
('Barreleye eyes can rotate inside a transparent fluid-filled shield.', 'https://www.mbari.org/news/researchers-solve-mystery-of-deep-sea-fish-with-tubular-eyes-and-transparent-head/', 'verified', 'MBARI reports ROV and aquarium observations.'),
('The featured barreleye was observed around 600–800 meters.', 'https://www.mbari.org/news/researchers-solve-mystery-of-deep-sea-fish-with-tubular-eyes-and-transparent-head/', 'verified', 'MBARI gives the ROV observation range.'),
('The fragile shield was likely destroyed in many net-collected specimens.', 'https://www.mbari.org/news/researchers-solve-mystery-of-deep-sea-fish-with-tubular-eyes-and-transparent-head/', 'verified-as-explanation', 'MBARI says this probably explains its absence from older descriptions.')]
},
7: {
'opening': "The deepest confirmed fish is not a giant fanged predator. It is a pale, soft snailfish filmed at 8,336 meters. The internet's rule that every level gets creepier breaks before the trench floor.",
'pov': "[HUMAN] That record broke my own 'deeper means scarier' rule. The animal looks more delicate than monstrous, which is exactly why a depth-by-depth horror ladder is such a bad biology lesson.",
'structure_title': "Descend until the horror story fails",
'structure': "In the twilight zone, faint light still rewards large eyes, transparency, silvering, and counter-illumination. In the midnight zone, complete darkness and scarce food reward lures, low-energy movement, and large feeding equipment in some predators. On abyssal plains, slow scavengers, deposit feeders, jellies, and sea cucumbers are common. In trenches, amphipods, sea cucumbers, microbes, and snailfish dominate many observations. The environmental gradient is real. The guaranteed progression from normal to monster is not.",
'visual': "Make this a descending counterexample. At each zone, show the trait the viewer expects and then the trait the habitat actually rewards. End on the deepest confirmed fish rather than a dramatic predator. The visual rhythm should slow as the depth increases, matching the shift toward lower-energy life instead of accelerating into a horror-game finale.",
'boundary': "Some deep animals are large or heavily armed, and deep-sea gigantism occurs in certain groups. That does not mean animals generally become larger, more aggressive, or more grotesque with depth. Sampling also biases what becomes famous: a fanged fish makes a better thumbnail than a sediment-eating sea cucumber. The deepest confirmed fish record is one filmed snailfish; it does not describe every trench community.",
'closing': "Depth changes the rules, not the genre. The deeper ocean contains predators, but it also contains soft fish, drifting jellies, scavengers, microbes, and animals living on falling particles. The horror ladder is a storytelling device. The ecological gradient is the real story.",
'variation': 'Zone-by-zone descent that ends with a counterexample rather than escalation.',
'claims': [
('The deepest confirmed fish sighting is a snailfish at 8,336 meters.', 'https://oceanexplorer.noaa.gov/ocean-fact/what-is-the-deepest-living-fish/', 'verified', 'NOAA updated page published January 2026.'),
('Research suggests a likely fish depth boundary around 8,200–8,400 meters.', 'https://oceanexplorer.noaa.gov/ocean-fact/what-is-the-deepest-living-fish/', 'verified-with-context', 'A physiological research estimate, not an absolute law for all future observations.'),
('The midnight zone begins near 1,000 meters in common zone schemes.', 'https://www.whoi.edu/ocean-learning-hub/ocean-topics/how-the-ocean-works/ocean-zones/midnight-zone/', 'verified-with-context', 'Zone boundaries are approximate.')]
},
8: {
'opening': "The deep sea is not an empty black room with one anglerfish in it. It is open water, canyon walls, abyssal mud, seamounts, vents, whale falls, and trenches—each with a different community.",
'pov': "[HUMAN] Once I stopped building the list around thumbnail-friendly predators, the deep sea became much stranger: colonies, jellies, worms, microbes, scavengers, and animals that barely fit the categories we use on land.",
'structure_title': "A habitat tour instead of a creature list",
'structure': "Begin in midwater with lanternfishes, bristlemouths, squid, krill, siphonophores, and jellies. Move to slopes and canyons with corals, sponges, rattails, octopuses, and crustaceans. Cross abyssal plains with sea cucumbers, brittle stars, worms, microbes, and scavengers. Visit vents and seeps where chemosynthetic microbes support tubeworms, mussels, crabs, and snails. End in trenches with amphipods, sea cucumbers, specialized snailfish, and microbial communities. The list changes because habitat matters as much as depth.",
'visual': "Use a map-like journey with a persistent depth and habitat label. Avoid rapid-fire stock montages that imply every animal shares the same water. A siphonophore in open midwater, a coral on a seamount, and a snailfish in a trench belong to different scenes. The viewer should leave with a mental map, not just twenty disconnected names.",
'boundary': "No short episode can inventory the deep sea. Many species remain undescribed, and sampling is uneven across oceans and habitats. 'Lives in the deep sea' can mean a permanent resident, a daily migrant, a life stage, or an animal that ranges across zones. The script should use examples, not imply a complete census or fixed universal community.",
'closing': "The deep sea is a set of connected neighborhoods, not one habitat. Animals move energy between them through migration, predation, scavenging, sinking particles, and chemical production. The next useful question is not only what lives down there, but where—and what that place demands.",
'variation': 'Geographic habitat tour with persistent depth labels, not a ranked animal montage.',
'claims': [
('The deep ocean generally begins around 200 meters in NOAA educational material.', 'https://oceanexplorer.noaa.gov/ocean-fact/deep-ocean/', 'verified-with-context', 'Broad zone definition.'),
('Hydrothermal vents were first discovered in 1977 near the Galápagos spreading ridge.', 'https://oceanservice.noaa.gov/facts/vents.html', 'verified', 'NOAA National Ocean Service.'),
('The deepest confirmed fish sighting is 8,336 meters.', 'https://oceanexplorer.noaa.gov/ocean-fact/what-is-the-deepest-living-fish/', 'verified', 'NOAA 2026 summary.')]
},
9: {
'opening': "My answer is the anglerfish—but not because it is the most dangerous. It is the fastest visual shortcut to fear: a mouth, exposed teeth, darkness, and a light that appears to bait something toward it.",
'pov': "[HUMAN] The anglerfish wins my personal fear test. I also know that is a reaction to a close-up image, not a scientific ranking and not evidence that it poses the greatest danger to humans.",
'structure_title': "Build the fear ranking honestly",
'structure': "Use four criteria: face, scale, movement, and uncertainty. Anglerfish score high on face. Giant squid score high on scale and rarity. Dragonfish and viperfish score high on exposed teeth. Giant isopods turn a familiar land shape into something much larger. Vampire squid win on name but lose on behavior; they are detritus feeders, not blood-drinking predators. The ranking can be personal as long as the script separates emotional response from ecology.",
'visual': "Put the criteria on screen and let the ranking change as context returns. A tight anglerfish face can lead, then scale information can reduce the perceived threat. A giant squid silhouette can raise it again. The final shot should be the environment itself—black water and a submersible light cone—because uncertainty is doing as much work as the animals.",
'boundary': "There is no objective scariest species. Many famous images remove scale, and several animals grouped under a common name differ greatly in size and behavior. The script can state a personal choice and compare documented traits. It cannot convert that choice into a scientific fact or imply routine danger to humans where no such evidence exists.",
'closing': "The scariest deep-sea creature is partly an animal and partly the story our brain writes around it. My vote is the anglerfish. The science answer is that fear depends on the feature you react to—and the context the photograph leaves out.",
'variation': 'Transparent first-person ranking with explicit criteria and context reversals.',
'claims': [
('Anglerfish use a lure to attract prey.', 'https://oceantoday.noaa.gov/creaturesofthedeep_anglerfish/', 'verified', 'NOAA educational source.'),
('Giant squid are rarely observed alive and are large deep-ocean predators.', 'https://ocean.si.edu/ocean-life/invertebrates/giant-squid', 'verified-with-context', 'Avoid exact maximum-size claims unless tied to measured specimens.'),
('Vampire squid feed largely on marine detritus rather than blood.', 'https://www.mbari.org/animal/vampire-squid/', 'verified', 'MBARI animal profile; footage rights remain separate from factual citation.')]
},
10: {
'opening': "Challenger Deep is about 10,935 meters below mean sea level. The honest version of that sentence includes six more meters: plus or minus six, at a 95 percent confidence interval.",
'pov': "[HUMAN] I kept seeing the depth repeated as one perfect number. The measurement paper is more interesting because it shows how much pressure calibration, gravity correction, water level, and uncertainty sit behind that clean figure.",
'structure_title': "How a depth becomes a number",
'structure': "A ship can map the trench with sonar, but a maximum depth depends on where the track crosses the seafloor and how sound speed is corrected. A submersible can infer depth from pressure, but that requires corrections for water properties, atmospheric pressure, gravity, gravity gradients, and sea level. The 2021 analysis used submersible transects from June 2020 and reported the deepest observed seafloor at 10,935 meters below mean sea level, with an uncertainty of plus or minus six meters at 95 percent confidence. The uncertainty is not a weakness. It is part of the measurement.",
'visual': "Build the episode as a measurement detective story. Start with the famous number, then peel back sonar, pressure sensors, gravity, and seafloor shape. Compare the average ocean depth of 3,682 meters with Challenger Deep, but avoid the usual 'Everest fits' line unless the mountain and trench reference levels are explained carefully.",
'boundary': "Challenger Deep is the deepest known seafloor depression measured with current methods, not a guarantee that every point of the ocean has been mapped at equal resolution. The seafloor is irregular, surveys follow finite tracks, and different methods can produce slightly different results. The reported 10,935-meter figure belongs with its uncertainty and reference to mean sea level.",
'closing': "The deepest part of the ocean is not just a place. It is a measurement problem under almost eleven kilometers of water. The number matters, but the corrections behind it are what turn a dramatic claim into evidence.",
'variation': 'Measurement detective story centered on uncertainty rather than a depth countdown.',
'claims': [
('Average ocean depth is about 3,682 meters.', 'https://oceanservice.noaa.gov/facts/oceandepth.html', 'verified', 'NOAA National Ocean Service.'),
('Challenger Deep is approximately 10,935 meters below mean sea level.', 'https://oceanservice.noaa.gov/facts/oceandepth.html', 'verified', 'NOAA summary.'),
('The 2021 pressure-derived study reports 10,935 m ±6 m at 95% confidence.', 'https://repository.library.noaa.gov/view/noaa/33477', 'verified', 'Peer-reviewed paper archived by NOAA.')]
},
11: {
'opening': "A finned octopus was filmed at 6,957 meters—nearly seven kilometers down—moving in water that our machines enter only with full-ocean-depth engineering. It had not survived a descent. It was already home.",
'pov': "[HUMAN] The detail that stays with me is not the record by itself. It is that the octopus is simply moving in the place our equipment struggles to reach.",
'structure_title': "The record changes the map",
'structure': "Before the 2020 paper, the deepest unambiguous photographic evidence for a cephalopod was 5,145 meters. Jamieson and Vecchione reported HD lander video of Grimpoteuthis at 5,760 and 6,957 meters in the Indian Ocean. That extended the confirmed in-situ depth by 1,812 meters and increased the potential benthic habitat available to cephalopods from an estimated 75 to 99 percent of the global seafloor. The key word is potential. One observation does not prove that every finned octopus occupies every trench.",
'visual': "Open with the depth record, then move backward into anatomy: fins, webbed arms, soft tissue, and the absence of lungs. This reverses the usual creature-profile order. Use an original silhouette and depth track unless a specific external clip is commercially admitted. The source paper itself is CC BY, but that does not automatically license every image or video appearing elsewhere online.",
'boundary': "The 6,957-meter record is a confirmed observation of one Grimpoteuthis individual, not the universal depth range of every animal called a dumbo octopus. 'Dumbo octopus' is a nickname for multiple cirrate species. The video proves coordinated presence at that site and depth; it does not reveal a complete diet, population size, reproductive cycle, or global distribution.",
'closing': "A dumbo octopus is not impressive because it looks cute under pressure. It is impressive because a soft, finned body can function at a depth that rewrote the known cephalopod map. The record is narrow, and it is still extraordinary.",
'variation': 'Record-first narrative that moves backward from depth to anatomy.',
'claims': [
('Grimpoteuthis was observed at 5,760 and 6,957 meters.', 'https://repository.library.noaa.gov/view/noaa/29154', 'verified', 'Peer-reviewed 2020 paper.'),
('The observations extended confirmed cephalopod depth by 1,812 meters.', 'https://repository.library.noaa.gov/view/noaa/29154', 'verified', 'Explicit in abstract.'),
('The paper estimated potential benthic habitat increased from 75% to 99% of global seafloor.', 'https://repository.library.noaa.gov/view/noaa/29154', 'verified-with-context', 'Potential habitat estimate, not occupancy.')]
},
12: {
'opening': "The frilled shark looks ancient. That does not mean it stopped evolving 80 million years ago. 'Living fossil' is a visual shortcut, not a time machine.",
'pov': "[HUMAN] I almost kept the 'unchanged for 80 million years' line because it is clickable. I cut it because an ancient-looking body is not proof that evolution stopped.",
'structure_title': "Start by removing the best clickbait line",
'structure': "The frilled shark is real enough without a false evolutionary freeze. Its long body, frill-like gill openings, flexible jaws, and three-pronged teeth create an eel-like profile unlike familiar sharks. Smithsonian notes that its feeding behavior has not been directly observed and describes swallowing large prey as a scientific interpretation based on anatomy. That distinction is the episode: a body can support a hypothesis without giving us a complete behavior sequence.",
'visual': "Use anatomy labels and a silhouette comparison with a typical shark. Do not animate a speculative lunge as if it were filmed behavior. If a reconstruction is shown, label it clearly. This episode's structural variation is to correct the viral claim first, then earn back the viewer's interest with what the evidence genuinely supports.",
'boundary': "The phrase 'living fossil' can suggest that a modern species is identical to an ancient ancestor or has stopped evolving. That is not supported. The frilled shark belongs to an old lineage and retains features people describe as primitive, but the living species has its own evolutionary history. Feeding behavior remains poorly observed, so claims about striking like a snake or swallowing a particular fraction of body size should be presented as hypotheses unless tied to direct evidence.",
'closing': "The frilled shark does not need an 80-million-year freeze to be compelling. It is a modern animal with an unfamiliar body, rare observations, and a feeding story that anatomy suggests but cameras have barely tested.",
'variation': 'Myth correction before creature reveal; anatomy hypotheses labeled as inference.',
'claims': [
('Frilled sharks have a snakelike body, three-pronged teeth, and frill-like gills.', 'https://ocean.si.edu/ocean-life/sharks-rays/frilled-shark', 'verified', 'Smithsonian profile.'),
('Feeding behavior has not been directly observed in the Smithsonian summary.', 'https://ocean.si.edu/ocean-life/sharks-rays/frilled-shark', 'verified', 'The page explicitly notes this.'),
('The “unchanged for 80 million years” claim is excluded.', 'https://ocean.si.edu/ocean-life/sharks-rays/frilled-shark', 'corrected', 'No support for evolutionary stasis; the script rejects the claim.')]
},
13: {
'opening': "Below the reach of sunlight, much of the light you see is made by life. It can hide a silhouette, lure prey, warn a predator, find a mate, or send a signal we still do not understand.",
'pov': "[HUMAN] I kept wanting to say 'three quarters of deep-sea animals glow.' The MBARI figure is powerful, but it comes from animals their ROV surveys could observe, not a census of every species in the ocean.",
'structure_title': "One chemistry, many jobs",
'structure': "Bioluminescence is light produced by a chemical reaction, often involving a light-emitting molecule called a luciferin and an enzyme or photoprotein. The exact chemistry varies among organisms. In blue-dominated seawater, blue-green light often travels efficiently, which helps explain the color of many marine signals. The same ability can serve opposing roles: an anglerfish lure attracts, counter-illumination hides, a flash can startle, and a glowing cloud can distract. A single animal may use more than one function.",
'visual': "This episode should feel like a mechanism demonstration. Begin with darkness, add the chemical reaction as a clean original animation, then reuse the same burst of light in four contexts: lure, camouflage, warning, and communication. That structural repetition has meaning; the surrounding behavior changes the function. Do not use MBARI footage unless the individual asset has commercial rights clearance.",
'boundary': "MBARI reports that 76 percent of observed water-column creatures and 45 percent of observed bottom-dwelling creatures in its ROV work could produce light, from the surface to 4,000 meters. Those percentages describe the surveyed animals researchers could see and classify. They are not a universal species census. Fluorescence is also different from bioluminescence: fluorescence re-emits incoming light, while bioluminescence generates light chemically.",
'closing': "The deep ocean is dark, but it is not visually silent. Life supplies its own signals. The useful question is not only which animal glows, but what that light is doing at that exact moment.",
'variation': 'Chemistry-first explainer that reuses one light animation for four biological functions.',
'claims': [
('MBARI reports 76% of observed water-column creatures could make light.', 'https://www.mbari.org/project/bioluminescence-and-fluorescence/', 'verified-with-context', 'Survey/observation statistic, not all species.'),
('MBARI reports 45% of observed bottom-dwelling creatures could make light.', 'https://www.mbari.org/project/bioluminescence-and-fluorescence/', 'verified-with-context', 'Survey/observation statistic.'),
('The MBARI observation range extended from the surface to 4,000 meters.', 'https://www.mbari.org/project/bioluminescence-and-fluorescence/', 'verified', 'Explicit on project page.')]
},
14: {
'opening': "The biggest colossal squid claims usually describe an animal nobody has measured. The safest numbers come from specimens, and the most famous intact specimen weighed 495 kilograms and measured about 4.2 meters.",
'pov': "[HUMAN] The hardest part of this script was refusing the biggest number on the internet. A measured specimen and a projected maximum are not the same thing.",
'structure_title': "Measure the specimen before imagining the monster",
'structure': "Colossal squid and giant squid are different animals. Colossal squid have a heavier body, rotating hooks on parts of the arms and tentacles, a beak, and extremely large eyes. But live behavior remains poorly documented. Museums can measure a specimen's mass, mantle, arms, tentacles, beak, and eyes. Estimates of a theoretical maximum use incomplete specimens, beaks found in predator stomachs, and assumptions about body proportions. Those projections may be useful, but they should not be narrated as if a complete animal was placed on a scale.",
'visual': "Build the episode around a measurement table rather than a sea-monster silhouette. Mark which values are directly measured, which come from a specimen, and which are inferred. Use original diagrams. Te Papa's pages are excellent factual references, but at least one displayed specimen image is marked CC BY-NC-ND, which is not acceptable for a monetized modified video.",
'boundary': "Size records depend on whether the claim refers to mass, total length, mantle length, or eye diameter. Damaged and contracted specimens complicate length. The 495-kilogram, roughly 4.2-meter animal is a measured specimen associated with Te Papa; it does not prove a species maximum. Claims that colossal squid have the largest eyes should remain tied to measured or documented specimens and not become a universal exact record without a current source.",
'closing': "The colossal squid is enormous without borrowing a fictional maximum. The most honest version separates the animal on the table from the animal we imagine in the dark—and tells the viewer which number belongs to which one.",
'variation': 'Specimen-led measurement audit; measured and projected values use different on-screen labels.',
'claims': [
('Te Papa holds three colossal squid specimens and displays one.', 'https://www.tepapa.govt.nz/digital-museum/explore-digital-museum/colossal-squid', 'verified', 'Te Papa collection page.'),
('Te Papa measured the displayed colossal squid at 495 kg and 4.2 m total length after thawing.', 'https://www.tepapa.govt.nz/digital-museum/explore-digital-museum/colossal-squid/colossal-squid-te-papa/how-big-colossal-squid-on', 'verified-with-context', 'Te Papa notes postmortem shrinkage and specimen treatment complicate length comparisons.'),
('Te Papa says little is known about life history, diet, and behavior.', 'https://www.tepapa.govt.nz/digital-museum/explore-digital-museum/colossal-squid', 'verified', 'Explicit on collection page.')]
},
15: {
'opening': "The famous 'only four people have reached Challenger Deep' line is outdated. The engineering is still rare. The visitor count is not a stable fact anymore.",
'pov': "[HUMAN] I had to delete a cleaner title because it stopped being true. That is exactly the kind of correction this channel needs to make before the audience makes it for us.",
'structure_title': "A descent built around one protected bubble",
'structure': "A crewed full-ocean-depth submersible keeps its occupants near surface pressure inside a small, rigid sphere. Everything outside that sphere—batteries, cameras, lights, syntactic foam, thrusters, cables, and viewports—must tolerate or isolate extreme pressure. Trieste reached the bottom in 1960. Modern vehicles add repeatability, better navigation, higher-resolution imaging, sampling, and pressure-derived depth measurements. Repeated dives turn a singular stunt into a survey platform.",
'visual': "Use an engineering cutaway rather than a celebrity count. Start with the pressure sphere, expand outward to the vehicle, then show the descent timeline from surface to trench floor. The viewer should understand why the cabin is small, why buoyancy material matters, and why a return trip depends on systems that cannot be casually repaired at depth.",
'boundary': "Do not publish a total number of people who have reached Challenger Deep unless it is checked immediately before release against a current, authoritative log. The count changes. Depth values also depend on method and uncertainty. The stable claims are the 1960 Trieste descent, the approximate 10,935-meter depth estimate, and the engineering requirement for full-ocean-depth pressure protection.",
'closing': "Reaching Challenger Deep is not impressive because the guest list is short. It is impressive because every life-supporting centimeter has to work beneath nearly eleven kilometers of water—and still bring the people inside back to the surface.",
'variation': 'Engineering cutaway and descent timeline; no visitor-count hook.',
'claims': [
('Trieste reached Challenger Deep in 1960.', 'https://oceanexplorer.noaa.gov/history/quotes-soundings/', 'verified', 'NOAA history source in repository.'),
('The revised maximum depth estimate is 10,935 m ±6 m at 95% confidence.', 'https://repository.library.noaa.gov/view/noaa/33477', 'verified', '2021 peer-reviewed study.'),
('A current total visitor count is intentionally omitted.', 'https://repository.library.noaa.gov/view/noaa/33477', 'corrected', 'The research source establishes depth, not a stable visitor count.')]
},
16: {
'opening': "A whale can die once and feed a deep-sea community for decades. First the flesh goes. Then the enriched sediment. Finally, microbes unlock energy trapped inside the bones.",
'pov': "[HUMAN] I expected the dramatic part to be the sharks and hagfish. The part I did not expect was the bone stage—an energy reserve that can keep supporting life long after the carcass stops looking like food.",
'structure_title': "One body, three ecological chapters",
'structure': "The first chapter belongs to mobile scavengers that remove soft tissue. Smithsonian says this phase can last up to about two years. The enrichment-opportunist phase follows as worms, crustaceans, and mollusks use leftovers and nutrient-rich sediment, also on the order of years. The sulfophilic stage can last decades. Bacteria break down lipids in bones and generate reduced chemicals that support additional microbes and animals. The carcass shifts from meal to habitat.",
'visual': "Use a time-lapse structure with the same whale silhouette changing across years. Keep the phases on screen and avoid pretending that every whale fall follows the same exact clock. Original diagrams can show the succession without using copyrighted documentary footage. If real whale-fall footage is added, its license must be admitted clip by clip.",
'boundary': "Stage names and time ranges are simplified models. Duration depends on whale size, depth, temperature, oxygen, burial, scavenger access, and local community. The phases can overlap rather than switching cleanly. A whale fall supports a rich ecosystem, but it is not accurate to claim that every carcass produces the same species sequence or lasts the same number of years.",
'closing': "A whale fall is not one feeding event. It is ecological succession written across flesh, sediment, and bone. By the time the skeleton becomes the main energy source, the animal has been gone for years and the ecosystem it created is still working.",
'variation': 'Ecological succession told as a long time-lapse across three overlapping phases.',
'claims': [
('Mobile scavengers may feed on soft tissue for up to about two years.', 'https://ocean.si.edu/ocean-life/marine-mammals/life-after-whale-whale-falls', 'verified-with-context', 'Smithsonian educational summary; timing varies.'),
('The enrichment-opportunist phase is described as around two years.', 'https://ocean.si.edu/ocean-life/marine-mammals/life-after-whale-whale-falls', 'verified-with-context', 'Simplified phase timing.'),
('The sulfophilic stage can last decades.', 'https://ocean.si.edu/ocean-life/marine-mammals/life-after-whale-whale-falls', 'verified', 'Smithsonian summary.')]
},
17: {
'opening': "The yeti crab does not carry a garden. It waves bacteria-covered claws through chemical-rich water, then harvests the growth. 'Farming' sounds cute until you see the isotope evidence behind it.",
'pov': "[HUMAN] I thought 'farming bacteria' was just a metaphor. The lipid and isotope evidence is why the phrase belongs here at all.",
'structure_title': "From strange dance to tested diet",
'structure': "Researchers described Kiwa puravida in a 2011 peer-reviewed paper. The crab waves bacteria-covered chelipeds in fluid escaping from a methane seep. The authors tested whether those epibiotic bacteria were a main food source using lipid and isotope analyses, and they described specialized setae used to harvest the bacteria. The behavior, anatomy, and chemistry point in the same direction. The word farming remains an interpretation, but it is not based on appearance alone.",
'visual': "Structure the episode like a research-paper detective story: behavior first, then anatomy, then chemical evidence. Label each evidence layer. An original animation can show boundary-layer flow over the claws and the harvesting motion. The PLOS paper is CC BY and its figures may be reusable with attribution, but any figure chosen still needs an asset record and exact credit.",
'boundary': "Not every yeti crab species uses the same microbial arrangement or behavior. Kiwa puravida was described from Costa Rican methane seeps at about 1,000–1,040 meters, while other kiwaids live in different vent and seep settings. The paper supports bacteria as a major food source for this species; it does not establish identical farming behavior across the whole family.",
'closing': "The yeti crab story works because three kinds of evidence agree: what the crab does, what its body is built to do, and what its tissues say it has eaten. The dance is memorable. The tested diet is the reason it is science.",
'variation': 'Research-paper detective sequence: behavior → anatomy → isotope evidence.',
'claims': [
('Kiwa puravida paper published in 2011; the family was first described in 2005.', 'https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0026243', 'verified', 'PLOS paper.'),
('The species waves bacteria-covered claws in methane-seep fluid.', 'https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0026243', 'verified', 'Observed behavior described in abstract and paper.'),
('Study sites were about 1,000–1,040 meters deep.', 'https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0026243', 'verified', 'Methods section.')]
},
18: {
'opening': "Hydrothermal vent fluid can exceed 340 degrees Celsius and remain liquid. The boiling point you learned at sea level is not a universal switch. Pressure moves it.",
'pov': "[HUMAN] I used to hear 'water hotter than boiling that does not boil' as a magic trick. The pressure explanation makes it more impressive, not less.",
'structure_title': "Boiling is a pressure question",
'structure': "At sea level, water boils near 100 degrees Celsius because its vapor pressure can match the surrounding atmosphere. Deep underwater, the surrounding pressure is much greater, so liquid water can remain stable at far higher temperatures. Seawater moves through cracks, is heated near magma, reacts with rock, and rises. When the hot fluid meets near-freezing seawater, dissolved minerals precipitate into dark particles and build black-smoker chimneys.",
'visual': "Use a pressure-versus-boiling diagram and a cutaway through ocean crust. Do not depict the vent as a hollow underwater volcano. Show seawater circulation, heating, chemical reaction, and mineral precipitation. The black plume is a particle cloud, not smoke from combustion. This physics-first structure should look completely different from the preceding animal episode.",
'boundary': "Vent temperatures vary, and NOAA's current public fact page says seawater may exceed 340°C—not that every black smoker is exactly 340°C or 400°C. The fluid can also enter supercritical regimes depending on pressure, temperature, and salinity; this short script does not model that full phase chemistry. Animals do not live inside the hottest jet. They occupy gradients and mixing zones around the vent.",
'closing': "Black-smoker water does not ignore boiling. It obeys a different pressure condition. The hot fluid, cold ocean, and dissolved minerals meet in seconds—and the chimney records that meeting layer by layer.",
'variation': 'Physics-first cutaway with pressure/boiling diagram; no creature-led opening.',
'claims': [
('Vent seawater may exceed 700°F / 340°C.', 'https://oceanservice.noaa.gov/facts/vents.html', 'verified', 'NOAA National Ocean Service.'),
('Hot vent water does not boil because of extreme pressure.', 'https://oceanservice.noaa.gov/facts/vents.html', 'verified', 'Explicit NOAA statement.'),
('Hydrothermal vents were first discovered in 1977 near the Galápagos ridge.', 'https://oceanservice.noaa.gov/facts/vents.html', 'verified', 'NOAA historical note.')]
},
19: {
'opening': "The deepest fish ever filmed was a snailfish at 8,336 meters. The deepest fish ever caught was recorded at 8,022 meters. Those are different records, and the distinction matters.",
'pov': "[HUMAN] The record only made sense once I separated 'filmed' from 'caught.' The filmed animal was not collected, so even its species identification remains cautious.",
'structure_title': "Two records, two standards of proof",
'structure': "In the Izu-Ogasawara Trench, researchers filmed a solitary juvenile snailfish at 8,336 meters. No specimen was captured, so the paper identifies it as probably Pseudoliparis belyaevi or a new endemic species. In the neighboring Japan Trench, two P. belyaevi specimens were collected at 8,022 meters, setting the deepest-caught record. Video proves an animal was present and moving at a measured depth. A specimen allows stronger anatomical and genetic identification. Neither evidence type is automatically better for every question.",
'visual': "Split the screen into FILMED and CAUGHT. Keep the depth, trench, and evidence type visible. Then show the proposed physiological boundary around 8,200–8,400 meters as a shaded range, not a brick wall. This turns the episode into a record audit rather than a simple countdown.",
'boundary': "The 8,336-meter animal was probably a known snailfish or a new endemic species because no physical specimen was taken. A 1970 cusk-eel trawl reached deeper, but NOAA notes uncertainty about where in the trawl path the fish was caught. Research suggests a fish depth boundary around 8,200–8,400 meters, but a future observation could refine the range.",
'closing': "The deepest-fish record is not one number. It is a chain of evidence: depth, camera, specimen, trench, and identification. Keeping those pieces separate makes the record more credible—and makes the remaining kilometer to Challenger Deep even more biologically interesting.",
'variation': 'Record dispute presented as FILMED versus CAUGHT evidence lanes.',
'claims': [
('Deepest confirmed fish sighting: snailfish at 8,336 meters.', 'https://research-repository.uwa.edu.au/en/publications/new-maximum-depth-record-for-bony-fish-teleostei-scorpaeniformes-/', 'verified', 'Peer-reviewed 2023 paper.'),
('Deepest caught fish specimens: P. belyaevi at 8,022 meters.', 'https://research-repository.uwa.edu.au/en/publications/new-maximum-depth-record-for-bony-fish-teleostei-scorpaeniformes-/', 'verified', 'Paper reports two specimens.'),
('Likely fish physiological boundary around 8,200–8,400 meters.', 'https://oceanexplorer.noaa.gov/ocean-fact/what-is-the-deepest-living-fish/', 'verified-with-context', 'Research estimate, not an absolute wall.')]
},
20: {
'opening': "At about 1,000 meters, the last sunlight is gone. The midnight zone continues to roughly 4,000 meters, holding around 70 percent of the ocean's water in permanent darkness.",
'pov': "[HUMAN] The name 'midnight zone' sounds like a clean border. The sources use approximate depths, and the real water column changes continuously rather than flipping a switch at exactly one kilometer.",
'structure_title': "One imagined hour in permanent night",
'structure': "There is no sunrise in the bathypelagic zone. Food arrives as sinking particles, falling carcasses, migrating animals, and prey. Light comes from organisms. Pressure ranges roughly from 100 to 400 atmospheres across the common 1,000-to-4,000-meter definition, while temperature is often near 4°C. Animals still need to find food, avoid predators, and reproduce. They use bioluminescence, sensitive eyes, sound, smell, patience, and low-energy movement in different combinations.",
'visual': "Give the viewer a slow hour rather than a fast zone list. Follow a particle of marine snow, a migrating animal passing through, a flash of bioluminescence, and a predator waiting in darkness. The pace should be quieter than the previous record video. Keep the depth gauge moving slowly to reinforce that the zone itself spans three vertical kilometers.",
'boundary': "The 1,000- and 4,000-meter boundaries are conventional approximations. Local light, temperature, oxygen, currents, and seafloor depth vary. WHOI describes the midnight zone as roughly 70 percent of all seawater, but that does not mean 70 percent of ocean species live there. ROV lights can also alter behavior, so what cameras observe is not a perfectly neutral window.",
'closing': "The midnight zone is not empty darkness. It is the largest dark habitat on the planet, full of signals our eyes usually miss and lives paced by food arriving from somewhere else. Its boundaries are approximate. Its scale is not.",
'variation': 'Slow “one hour in the zone” narrative instead of a taxonomy or record structure.',
'claims': [
('Midnight zone begins near 1,000 m and extends to about 4,000 m.', 'https://www.whoi.edu/ocean-learning-hub/ocean-topics/how-the-ocean-works/ocean-zones/midnight-zone/', 'verified-with-context', 'Conventional approximate boundaries.'),
('Temperature is around 4°C and pressure roughly 100–400 atmospheres across that zone.', 'https://www.whoi.edu/ocean-learning-hub/ocean-topics/how-the-ocean-works/ocean-zones/midnight-zone/', 'verified-with-context', 'WHOI educational ranges; local variation exists.'),
('WHOI describes the zone as roughly 70% of all seawater.', 'https://www.whoi.edu/ocean-learning-hub/ocean-topics/how-the-ocean-works/ocean-zones/midnight-zone/', 'verified-with-context', 'Volume statement, not species abundance.')]
}

}

KEEP = {
1:['The right way to see it','Their bodies solve a different set of problems','Darkness changes eyes, color, and communication','Scarce food favors oversized feeding equipment','Soft bodies can be an advantage under pressure','Common myths and questions'],
2:['The right way to see it','Pressure acts most dramatically on gas','They are built for one pressure regime','Vertical migrants tolerate large daily changes','Why humans and submersibles need protection','Common myths and questions'],
3:['The right way to see it','Most upward movement is normal','A viral surface sighting may be a different phenomenon','One observation does not establish a global trend','What researchers would check','Common myths and questions'],
4:['The right way to see it','Our brains treat unfamiliar anatomy as a threat','The teeth are often about not losing one meal','Bioluminescence looks supernatural because we rarely see it','The deep sea is genuinely hazardous, but not mainly because of animals','Common myths and questions'],
5:['The right way to see it','Color depends on the light that reaches an object','Darkness can be camouflage','Not every red animal lives at the same depth','ROV lights reveal colors the animal does not normally display','Common myths and questions'],
6:['The right way to see it','Open water has nowhere to hide','Transparency is easier for some tissues than others','The barreleye uses transparency as a window, not whole-body camouflage','Transparency has limits','Common myths and questions'],
7:['The right way to see it','Depth changes the design constraints','The twilight zone still rewards visual camouflage','The midnight and abyss favor low-energy survival','Some of the deepest animals look less monstrous, not more','Common myths and questions'],
8:['The right way to see it','The deep sea is many habitats, not one empty place','Twilight-zone animals','Midnight and abyssal animals','Hadal trench animals','Common myths and questions'],
9:['The right way to see it',"'Scariest' is a human category",'Anglerfish: the iconic horror face','Dragonfish and viperfish: teeth that secure prey','Giant squid: fear created by scale and rarity','Giant isopods: familiar anatomy at unfamiliar scale','Common myths and questions'],
10:['The right way to see it','Challenger Deep lies inside the Mariana Trench','The best current estimate is about 10.9 kilometers','The bottom is dark, cold, and under extreme pressure','Exploration requires full-ocean-depth engineering','Common myths and questions'],
11:['A name that hides a whole group','The observation at 6,957 meters','A body built around water, not air','What the camera still cannot tell us'],
12:['The shark that breaks the familiar outline','Why living fossil is a dangerous shortcut','Anatomy suggests a feeding strategy, but cameras are scarce','A rare animal becomes a projection screen'],
13:["The ocean's darkness is not actually dark",'Water selects the color palette','The same chemistry can hide, hunt, warn, or lie','A percentage is not a census'],
14:['The word largest needs a measuring rule','Eyes built to detect a large moving signal','Rotating hooks, a beak, and very little live footage','A specimen is a library, not a movie'],
15:['A vehicle built around one protected bubble','Trieste reached the bottom before precision caught up','Repeatability changes exploration into measurement','Depth is a calculation with an uncertainty budget'],
16:['A single body changes a food-poor landscape','The first stage is large and fast','Bones store an energy reserve','From food island to hard substrate'],
17:['A family science met only recently','The dancing behavior that suggested cultivation','Chemistry, anatomy, and behavior point to the same meal','One family, several microbial arrangements'],
18:['One hundred degrees is not a universal boiling point','A circulation system inside the crust','The smoke is a mineral cloud','Life occupies the boundary, not the furnace'],
19:['A record made by a camera, not a net','The body avoids some obvious pressure problems','Trenches can concentrate food','The deepest trench floor may be beyond fish physiology'],
20:['A zone defined by depth and the end of sunlight','Most energy falls or swims down from above','Bioluminescence becomes the visual language','One name covers a wide physical gradient']
}


def parse_script(path: Path):
    text = path.read_text()
    title = text.splitlines()[0].removeprefix('# ').strip()
    article = re.search(r'\*\*Article:\*\*\s*(.+)', text).group(1).strip()
    direct = re.search(r'## Direct-answer lock\n\n(.*?)(?=\n## Narration)', text, re.S).group(1).strip()
    narration = re.search(r'## Narration\n(.*?)(?=\n## Chapters)', text, re.S).group(1)
    parts = re.split(r'(?m)^### ', narration)
    sections = {}
    for part in parts[1:]:
        name, body = part.split('\n', 1)
        sections[name.strip()] = body.strip()
    sources_tail = re.search(r'## Sources\n(.*)$', text, re.S).group(1).strip()
    return title, article, direct, sections, sources_tail


def words(text: str):
    return re.findall(r"\b[\w’'-]+\b", text)


def timestamp(seconds: float):
    seconds = int(round(seconds))
    return f'{seconds//60:02d}:{seconds%60:02d}'


def build(seq: int, path: Path):
    data = DATA[seq]
    title, article, direct, old, sources_tail = parse_script(path)
    sections = [('Cold open', data['opening']), ('Title card', title)]
    for name in KEEP[seq]:
        body = old.get(name)
        if body:
            # remove obvious repeated boilerplate sentence in first batch
            body = re.sub(r'\s*This matters because an adaptation is never just a visual effect\..*?water column\.', '', body, flags=re.S)
            sections.append((name, body.strip()))
    insert_at = 3 if len(sections) > 3 else len(sections)
    sections.insert(insert_at, ('Producer POV', data['pov']))
    sections.append((data['structure_title'], data['structure']))
    sections.append(('What to notice in the edit', data['visual']))
    sections.append(('Evidence limit', data['boundary']))
    sections.append(('Closing', data['closing']))

    narration_md = '\n\n'.join(f'### {name}\n\n{body}' for name, body in sections)
    narration_plain = '\n\n'.join(body.replace('[HUMAN] ', '') for _, body in sections)
    wc = len(words(narration_plain))
    duration = wc / 145 * 60
    chapter_lines=[]
    elapsed=0.0
    for name, body in sections:
        chapter_lines.append(f'- {timestamp(elapsed)} {name}')
        elapsed += len(words(body)) / 145 * 60

    md = f'''# {title}

**Status:** HUMANIZED EDITORIAL PASS COMPLETE — OWNER CONFIRMATION AND MASTER WATCH REQUIRED  
**Article:** {article}  
**Word count:** {wc}  
**Estimated narration:** {int(duration//60)}m {int(round(duration%60)):02d}s at 145 WPM  
**Humanization pass:** 2026-07-30

## Direct-answer lock

{direct}

## Narration

{narration_md}

## Human fingerprint gate

- Humanized cold open: COMPLETE — owner must confirm it sounds natural when read aloud.
- First-person producer observation: DRAFTED — owner must confirm it is genuinely her view before approval.
- Evidence uncertainty or limitation: COMPLETE.
- Structural variation: {data['variation']}
- Number-level source audit: COMPLETE for the key claims listed in `production/research/number-verification.md`.
- Final human watch-through: PENDING until the rendered MP4 exists.

## Chapters

{chr(10).join(chapter_lines)}

## Sources

{sources_tail}
'''
    path.write_text(md)
    (PLAIN / path.with_suffix('.txt').name).write_text(narration_plain.strip()+'\n')

    hp = HUMAN / path.name
    hp.write_text(f'''# Human Pass — Video {seq:02d}

**Query:** {title}  
**Canonical article:** `{article}`  
**Status:** HUMANIZED EDITORIAL PASS COMPLETE — OWNER CONFIRMATION AND MASTER WATCH PENDING

## Completed editorial work

- [x] Cold open rewritten into a unique spoken hook.
- [x] First-person producer POV drafted and inserted.
- [x] Evidence limit, correction, or uncertainty stated.
- [x] Structure varied from the previous episode.
- [x] Repetitive production scaffolding removed.
- [x] Key numerical claims mapped to named sources.
- [x] Markdown and Kokoro plaintext synchronized.

## Owner confirmation still required

- [ ] Read the cold open aloud and confirm it sounds like you.
- [ ] Confirm the `[HUMAN]` observation is genuinely your view; rewrite it if not.
- [ ] Listen to the Kokoro pronunciation of every scientific name and number.
- [ ] Watch the final rendered MP4 from beginning to end.
- [ ] Confirm title, thumbnail, pacing, rights, and source links before upload.
- [ ] Run `python production/automation/approve_human_pass.py --sequence {seq} --reviewer "YOUR NAME"` only after those checks.

## Structural variation

{data['variation']}

## Approval boundary

This file records an editorial pass, not final human approval. The approval ledger must remain pending until a real person confirms the POV and watches the finished master.
''')
    return {
        'sequence': seq,
        'slug': path.stem[3:],
        'title': title,
        'wordCount': wc,
        'estimatedDurationSeconds': int(round(duration)),
        'chapters': [{'time': line.split()[1], 'title': ' '.join(line.split()[2:])} for line in chapter_lines],
        'status': 'humanized-owner-confirmation-required',
        'humanizationVersion': '2026-07-30'
    }


def main():
    PLAIN.mkdir(parents=True, exist_ok=True)
    HUMAN.mkdir(parents=True, exist_ok=True)
    (ROOT / 'production/research').mkdir(parents=True, exist_ok=True)
    rows=[]
    audits=[]
    for seq, path in enumerate(sorted(FINAL.glob('[0-9][0-9]-*.md')),1):
        rows.append(build(seq,path))
        d=DATA[seq]
        for claim,url,status,note in d['claims']:
            audits.append({'sequence':seq,'slug':path.stem[3:],'claim':claim,'sourceUrl':url,'status':status,'note':note,'verifiedOn':'2026-07-30'})
    INDEX.write_text(json.dumps(rows,indent=2)+'\n')
    AUDIT_JSON.write_text(json.dumps({'verifiedOn':'2026-07-30','scope':'Key numerical and record claims in the 20 launch scripts','claims':audits},indent=2)+'\n')
    md=['# Twenty-Video Number and Record Verification','', '**Verified:** 2026-07-30','', 'This ledger checks the key numerical, depth, date, record, percentage, and phase-duration claims used in the launch scripts. It does not convert source-backed claims into guaranteed future facts. Records and counts that can change must be rechecked immediately before publication.','', '| Video | Claim | Status | Source | Editorial boundary |','|---:|---|---|---|---|']
    for a in audits:
        md.append(f"| {a['sequence']:02d} | {a['claim'].replace('|','/')} | `{a['status']}` | {a['sourceUrl']} | {a['note'].replace('|','/')} |")
    md += ['', '## Hard stop', '', 'Do not mark a script human-approved merely because this ledger passes. A real person must confirm the first-person POV, listen to the final voice, and watch the final MP4.']
    AUDIT_MD.write_text('\n'.join(md)+'\n')
    print(json.dumps({'scripts':len(rows),'claims':len(audits),'status':'humanized-editorial-pass-complete'},indent=2))

if __name__ == '__main__':
    main()
