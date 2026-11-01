# How do you tell if steel is hardened?

**Status:** DRAFT — OWNER CONFIRMATION AND MASTER WATCH REQUIRED
**Domain:** materials-and-manufacturing
**Opening:** stake-then-payoff
**Word count:** ~1830
**Estimated narration:** 12m 39s at 144.58 WPM (measured, loop/durations.py)

## YouTube title

A magnet cannot tell hardened steel

## Direct-answer lock

The dependable way to tell if steel is hardened is to measure its resistance to indentation, most often with a Rockwell C test that presses a diamond cone into the surface under 150 kilograms-force, a method standardized by ASTM International. A file that skids instead of biting is a useful shop screen, but it ranks only the surface. How deep the hardness runs, and why, needs a hardness traverse and a cross-section under a microscope.

## Narration

### Cold open

{{stat: 150 | kilograms-force | Rockwell C total test force | ASTM International}}
A quenched knife and a soft nail both cling to the same magnet. The dependable way to tell if steel is hardened is to measure its resistance to indentation, most often with a Rockwell C test that presses a diamond cone into the surface under 150 kilograms-force, a method standardized by ASTM International. That number settles one thing well: how hard the steel is at one small spot near the surface. It does not settle how deep the hardness runs. It does not show whether the part was tempered afterwards, or whether the steel a few centimetres away behaved the same way in the quench. Each of those needs its own kind of evidence. The cheap shop tests you may have heard of answer different questions again.

### Title card

How to tell if steel is hardened

### Hardening rearranges the inside and leaves the outside alone

{{thermal: 727 | eutectoid temperature}}
Start with what hardening physically does. Carbon steel is iron with a small fraction of carbon dissolved in it. Heat it past 727 degrees Celsius, the eutectoid temperature on the iron-carbon phase diagram, and the iron reorganizes into a crystal structure called austenite, which can hold much more carbon in solution. For many steels the hardening temperature sits somewhat above that line. The exact figure depends on the alloy, so a heat treater reads it from the data for that grade rather than from memory. Cool the steel slowly and the carbon has time to migrate out, forming softer, layered structures. Quench it fast, in water, brine or oil, and the carbon is trapped where it sits. The iron lattice tries to shift back to its room-temperature arrangement anyway. What results is a strained, distorted crystal called martensite.

{{define: martensite | the strained crystal that forms when quenching traps carbon in iron | hard and brittle as quenched, so it is tempered | ASM International}}
Martensite is what a hardened part is mostly made of, and it is why this question is harder than it sounds. ASM International's heat-treating references describe martensite as hard and brittle as quenched. That is why nearly every hardened tool is tempered afterwards: reheated to a moderate temperature to give up some hardness in exchange for toughness. None of this announces itself on the surface. A quenched blade keeps its shape, looks much the same once cleaned, and carries no visible label. Every practical test is therefore an indirect measurement of a structure you cannot see. The useful habit is to ask, for each test, which property of that structure it actually touches.

### A magnet and a temper colour are answering other questions

{{contrast: magnet test | is=a test for ferromagnetic steel | not=a test for hardened steel}}
The magnet is the most common shortcut, and it fails for a simple reason. Ordinary carbon steel is ferromagnetic whether it is soft, annealed or fully hardened, so the knife and the nail both pass. The magnet cannot tell you about heat treatment at all. What it does respond to is the family of crystal structure. Many austenitic stainless steels, the kind used for kitchen sinks, are essentially non-magnetic in the annealed state, and they also cannot be hardened by quenching. Martensitic stainless grades, used for many knife blades, are magnetic. So a magnet can sometimes hint at whether a steel is the kind that could be hardened. It says nothing about whether anyone has done it.

{{checklist: What a temper colour shows | +the surface was heated in air | -the steel was quenched first | ?how hard the steel is now}}
Temper colours are the second shortcut. When bright steel is heated in air, a thin oxide film grows on it. The film's thickness depends on temperature and time, and it produces colours running from pale straw through bronze and purple to blue. Smiths have long used those colours to judge tempering. But read carefully what they record: the surface was heated in air to some temperature. They do not show that the steel was quenched first, since soft mild steel colours the same way. And because time matters as well as temperature, a colour alone cannot tell you how hard the steel is now. Grinding or polishing removes the film entirely. The spark test, where a grinding wheel throws sparks whose bursts reflect carbon content, has the same character. It suggests whether a steel could be hardened, not whether it has been.

### Producer POV

[HUMAN] Once I can locate the failure — bad source, lazy assumption, missing context, evidence I ignored because it was inconvenient — I can let the belief go.

### A file ranks hardness by whether it can cut

{{steps: File test | Choose a sharp file | Draw it lightly across a clean edge | Feel whether it bites or skids | >It ranks the surface only}}
The file test is the oldest honest shortcut, because it actually tests hardness. A file is itself made of hardened steel. Choose a sharp file, draw it lightly across a clean edge of the part, and feel whether it bites or skids. If it bites, cutting bright metal with a slight drag, the part is softer than the file. If it skids across with a glassy feel and leaves almost no mark, the part is about as hard as the file, or harder. Industry still uses this as a screening check. Sets of files made to graded hardness exist, so that the skid point can be bracketed more closely.

{{contrast: file skid | is=evidence the surface is hard | not=evidence the whole part is hard}}
But notice what the file is touching: the outermost skin, and only where you dragged it. Two common situations break the inference. A case-hardened part, such as a carburized gear, has a hard shell over a deliberately softer core. The file skids, correctly, yet the core may be far softer than the skid suggests. The reverse happens with decarburization, when carbon is lost from the surface during heating in air. The skin turns soft while the interior stays hard, and the file bites a part that is, underneath, properly hardened. The result also depends on the file's sharpness and the pressure of your hand. So it ranks the surface only, and it ranks it against the file you happen to hold.

### A Rockwell number is a depth, read twice

{{chain: Rockwell C test | 10 kilograms-force preload | 150 kilograms-force total | depth difference | >Rockwell C number}}
The Rockwell C test replaces the hand with a machine and the feel with a depth. A diamond cone with a 120-degree tip is first pressed against the surface with a 10 kilograms-force preload. That seats the indenter and sets a zero below any surface roughness. Then the load rises to 150 kilograms-force total, is held briefly, and is reduced back to the preload. The machine records the depth difference between the two preload readings: how much permanent dent the full load left. A harder steel resists, the dent is shallower, and the Rockwell C number is higher. On this scale each point corresponds to two thousandths of a millimetre of depth. That is why the reading is so sensitive to dirt, scale and vibration.

{{stat: 150 | kilograms-force | Rockwell C total test force | ASTM International}}
ASTM International sets out the procedure in its standard for Rockwell testing of metallic materials, designated E18. It specifies the indenter, the forces, the dwell times, and rules a non-specialist would not think to ask about. The test piece must be thick enough that the dent does not reach the far side, or the anvil underneath is partly being measured. Indentations must be spaced away from edges and from each other, because each one disturbs the metal around it. Curved surfaces, like round bars, need corrections, because a cone sinks differently into a curve. A Rockwell number taken without those conditions met is a number, but not yet evidence.

{{contrast: Vickers test | is=a measured diagonal of a square diamond dent | not=a depth reading}}
Other methods trade convenience for different strengths. The Brinell test presses a hard ball into the metal and measures the width of the round impression, which averages over coarser structures but leaves a large mark. The Vickers test uses a square-based diamond pyramid and measures the diagonals of the dent under a microscope. With small loads it can place indentations a fraction of a millimetre apart, which matters for a question the file could never answer.

### A hardness number is only as good as the block behind it

{{sources: Reference blocks | NIST=produces Rockwell C reference test blocks | ASTM International=specifies how machines are verified against blocks}}
Here is the part of the chain most people never see. A hardness tester does not measure an absolute physical quantity the way a ruler measures length. The number depends on the exact geometry of the diamond, the accuracy of the forces, and the depth sensor. Two machines that differ slightly in any of those will disagree. So machines are checked against reference test blocks: pieces of steel prepared to be uniform and certified at a known hardness. NIST produces Rockwell C reference test blocks, calibrated on its own standardizing equipment, and the ASTM International standard specifies how machines are verified against blocks. When a lab reports a hardness, the defensible claim is that the machine read a certified block correctly that day, and then read your part.

{{ambient}}
That traceability is what turns the file's private judgement into a public measurement. Your hand cannot be sent to another laboratory. A certified block can.

### A cross-section shows why the number is high

{{steps: Metallographic check | Cross-section | Polishing | Nital etch | Microscope | >Martensite looks needle-like}}
Hardness tells you how much the metal resists; the microscope tells you why. A metallographer cuts a cross-section through the part, mounting it and polishing it flat, then gives it a nital etch. Nital is a dilute solution of nitric acid in alcohol. The acid attacks different structures at different rates, so the grain pattern appears. Under a microscope, properly hardened steel shows martensite, which looks needle-like or lath-like, fine and dense. Slowly cooled steel shows rounded grains and layered bands instead. Soft spots, where the quench was too slow, show up as patches of the wrong structure.

{{text}}
The same section answers the depth question the file could not. Run a line of small Vickers or Knoop indentations from the surface inward, and you get a hardness profile. On a case-hardened gear the numbers start high and fall off with depth. The depth at which they cross an agreed threshold is reported as the case depth. ASTM International publishes the microindentation method used for this kind of traverse. The cost is obvious: the part has been cut in half. In production, that is why a test coupon, or a sacrificial part from the same batch, carries the destructive evidence for the rest.

### What to notice in the edit

{{checklist: Tests in this episode | +file test ranks the surface | +Rockwell C test measures a depth | -magnet test detects hardening | ?case depth needs a cross-section}}
As you watch, notice where each diagram ends. The file test ranks the surface. The Rockwell C test measures a depth at one point, traced back to a certified block. Nothing in this episode shows that the magnet test detects hardening, which is why it never earns a place on the hardened side. And case depth needs a cross-section, which means some of the most important evidence about a hardened part is gathered on a different, destroyed piece of the same batch. The tests are not ranked from crude to good. Each one is matched to a narrower question than it first appears to answer.

### Evidence limit

{{contrast: hardness | is=resistance to one indenter under one load | not=toughness or wear life}}
A hardness reading does not establish that a part is fit for its job. It measures resistance to one indenter under one load at one spot. It does not measure toughness, so a part can read high and still crack in service if it was left untempered or tempered badly. It does not directly measure wear life or fatigue strength, which depend on structure, residual stress and surface finish as well. Conversions between Rockwell, Vickers and Brinell numbers come from published tables that are empirical and approximate, so a converted value is weaker evidence than a direct one. And none of these tests, alone, tells you the heat-treatment history that produced the result.

### Closing

{{ambient}}
So the knife and the nail are told apart by a dent, not by a magnet: a dent of a known depth, under a known force, from a machine that read a certified block that morning. Everything you want to say beyond that spot, you have to go and measure.

## Editorial gate

*What this episode does that a template would not. Every line below is a property the pipeline enforces at build time — see `loop/validate.py`. It records no step a human still owes.*

- Humanized cold open: PRESENT
- First-person producer observation: FROM POV BANK (pov-103)
- Evidence uncertainty or limitation: COMPLETE
- Structural variation: tests ordered by what each one physically touches, from no contact (magnet, colour) to surface skin (file) to measured depth (Rockwell) to full cross-section (microscope)
- Number-level source audit: COMPLETE

## Chapters

- 00:00 Cold open
- 00:48 Title card
- 00:51 Hardening rearranges the inside and leaves the outside alone
- 02:36 A magnet and a temper colour are answering other questions
- 04:24 Producer POV
- 04:35 A file ranks hardness by whether it can cut
- 06:12 A Rockwell number is a depth, read twice
- 08:25 A hardness number is only as good as the block behind it
- 09:29 A cross-section shows why the number is high
- 10:52 What to notice in the edit
- 11:34 Evidence limit
- 12:22 Closing

## Sources

- NIST: National Institute of Standards and Technology home page (hardness reference materials and standardization) — https://www.nist.gov/
- ASTM International: ASTM International home page (hardness test standards for metallic materials) — https://www.astm.org/
- ASM International: ASM International home page (heat treating and metallography references) — https://www.asminternational.org/
- MIT Department of Materials Science and Engineering: MIT DMSE home page (background on phase transformations in steel) — https://dmse.mit.edu/