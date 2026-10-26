# How to tell if steel is hardened?

**Status:** DRAFT — OWNER CONFIRMATION AND MASTER WATCH REQUIRED
**Domain:** materials-and-manufacturing
**Opening:** stake-then-payoff
**Word count:** ~1750
**Estimated narration:** 12m 6s at 144.58 WPM (measured, loop/durations.py)

## YouTube title

Steel hardness is a depth, not a colour

## Direct-answer lock

You tell whether steel is hardened by measuring how it resists indentation, not by looking at it: in the Rockwell C test, standardised by ASTM International, a diamond cone is pressed into the surface under a total of 150 kilograms-force, and the depth it reaches becomes the number. A file that skates instead of biting gives a fast first sign, but only about the surface. Confirming how deep the hardness goes, and that a quench produced it, takes a cut, polished and etched cross-section.

## Narration

### Cold open

{{stat: 150 | kilograms-force | the Rockwell C test | ASTM International}}
Two steel bars can look identical while one would snap like glass. You tell whether steel is hardened by measuring how it resists indentation, not by looking at it: in the Rockwell C test, standardised by ASTM International, a diamond cone is pressed into the surface under a total of 150 kilograms-force, and the depth it reaches becomes the number. That settles how hard the surface is at one spot. It does not settle how deep the hardness goes, whether it is even across the part, or how the steel got that way. Those are separate questions, and each one needs its own evidence.

### Title card

How to tell if steel is hardened

### Hardening changes the inside, so the outside barely tells you

{{define: hardened steel | steel quenched so its structure becomes martensite | tempering trades some hardness for toughness | ASM International}}
Start with what the word means. In metallurgy, hardened steel usually means steel quenched so its structure becomes martensite. The steel is heated until its iron rearranges into a phase called austenite, which can hold carbon in solution. Then it is cooled fast, in water, oil or brine. The carbon has no time to leave, so it is trapped inside a strained, distorted crystal. That trapped, strained lattice is martensite, and it is what makes the steel hard. ASM International, the professional society for metals and heat treatment, documents this sequence in its heat treating references, and materials courses, including those at MIT's Department of Materials Science and Engineering, teach it as a transformation that happens without the slow migration of atoms.

{{contrast: hardness | is=a measured resistance to indentation | not=a colour, a weight or a ring}}
None of that is visible. Hardness is a measured resistance to indentation. It is not a colour, a weight or a ring. A quench leaves scale and discolouration, but a bar can be discoloured by heating that never reached the right temperature, and a hardened bar can be ground clean and bright. The sound a bar makes when struck, and how heavy it feels in your hand, are traces of shape and process, not measurements of a property. Tempering adds another layer. Freshly quenched steel is usually too brittle to use, so it is reheated gently, and tempering trades some hardness for toughness. The thin oxide colours that appear during tempering, straw through to blue, are a rough guide to the temperature reached. They say nothing reliable about the hardness that resulted.

### A file gives a fast answer that can mislead

{{steps: The file test | Hold the file at a shallow angle | Draw it across a clean spot | Feel whether it bites or skates | >A skating file means hard at the surface, nothing more}}
The oldest shop test needs no instrument. Hold the file at a shallow angle. Draw it across a clean spot, ideally one that has been lightly ground. Feel whether it bites or skates. On soft steel, the teeth catch and raise chips. On fully hardened steel, the file slides across with a glassy feel, which is where the phrase file hard comes from. Toolmakers have relied on this for generations because it is fast, cheap and surprisingly consistent in practised hands. Calibrated test files are sold in sets meant to correspond to particular hardness levels, which turns a feeling into a rough bracket. But a skating file means hard at the surface, nothing more.

{{checklist: What the file test shows | +the surface resists cutting | -how deep the hardness goes | -a number another lab can repeat | ?whether the surface is decarburised}}
So consider what it actually tells you. The file test shows that the surface resists cutting. It does not show how deep the hardness goes. It does not give a number another lab can repeat. And it leaves open whether the surface is decarburised, meaning carbon burned out of the outer skin during heating, leaving a softer layer over a hard core. In that case the file bites, and you might wrongly conclude the whole part was never hardened. The test can fail in both directions.

### Producer POV

[HUMAN] Once I can locate the failure — bad source, lazy assumption, missing context, evidence I ignored because it was inconvenient — I can let the belief go.

### The Rockwell number is a depth, not the size of the dent

{{chain: Rockwell C test | 10 kilograms-force seats the cone | 150 kilograms-force total load | load returns to 10 kilograms-force | >depth difference becomes the number}}
The Rockwell test replaces feel with geometry. ASTM International publishes the method as standard E18. Under that standard, the C scale uses a diamond cone with a 120-degree point and a rounded tip. First, 10 kilograms-force seats the cone, pressing it just far enough to get past surface roughness and fix a reference depth. Then extra load is added, up to 150 kilograms-force total load. After a short dwell, the load returns to 10 kilograms-force, so the elastic spring-back of the steel is taken out of the reading. The machine measures how much deeper the cone now sits than it did at the reference. That depth difference becomes the number.

{{contrast: Rockwell C scale | is=a harder steel gives a higher number | not=a direct measure of strength}}
The scale runs opposite to depth, so a harder steel gives a higher number: the cone sinks less, and the reading rises. That is why hardened tool steels are discussed in Rockwell C values, while softer steels are tested on other scales with a ball indenter and a lighter load. A reading on one scale is not interchangeable with another. ASTM International publishes conversion tables, as standard E140, relating Rockwell, Brinell and Vickers values for particular classes of metal, but those tables are empirical. They come from side-by-side testing, not from theory, and the conversions are treated as approximate. Hardness also tracks tensile strength in a rough way, but it is not a direct measure of strength.

### A hardness number is only as good as its calibration

{{sources: Calibration chain | NIST=reference blocks for Rockwell hardness | ASTM International=the test method}}
Every Rockwell machine drifts. Diamonds chip, loads shift, anvils wear. So the number on the display is trusted only because of a chain standing behind it. ASTM International defines the test method. NIST, the United States national measurement laboratory, has produced standard reference blocks for Rockwell hardness, so that the test blocks used in industry can be tied back to a national reference. A lab checks its machine on certified blocks before it tests parts. If the machine reads the block within its stated tolerance, its readings on your part carry weight. If it does not, they do not, however precise they look.

{{steps: Before a valid reading | a flat, clean surface | enough thickness | indents spaced far enough apart}}
The specimen has to cooperate as well. The test assumes a flat, clean surface. It assumes enough thickness that the cone does not feel the anvil beneath. It assumes indents spaced far enough apart that one dent does not land in the work-hardened ring around another. Curved parts read differently from flat ones, and the standard provides corrections for them. Break any of these conditions and you can produce a confident number that describes your setup rather than your steel.

### A magnet answers a different question

{{thermal: 770 | Iron loses its magnetism}}
A common belief is that hardened steel is not magnetic, or that a magnet can sort hardened bars from soft ones. It cannot. The magnet's real use is during heating. Iron loses its magnetism at its Curie temperature, about 770 degrees Celsius, a figure documented in ASM International's references. Smiths heating simple carbon steels watch for the moment a magnet stops sticking, because for some of those steels it is a useful sign of being near the right heat to quench. It is a guide to the heat, not a test of the result.

{{contrast: the magnet test | is=a guide to the heat | not=a test of the result}}
Once the steel has been quenched, martensite is ferromagnetic. A properly hardened bar grabs a magnet just as the soft bar does. The exception runs the other way. Austenite is non-magnetic, and some austenite can survive a quench in high-carbon or heavily alloyed steels. Austenitic stainless steels are a separate family again: they are generally non-magnetic and are not hardened by quenching at all. So a magnet can hint at which phases are present, but sticking or not sticking tells you nothing reliable about whether ordinary carbon steel was hardened.

### A hard surface does not prove a hard core

{{define: case hardening | hardening only an outer layer, leaving a tougher core | the case depth must be measured on a cross-section | ASM International}}
Many parts are made hard only on the outside, on purpose. Case hardening means hardening only an outer layer, leaving a tougher core. Carburising diffuses extra carbon into the surface before the quench; induction hardening heats only the skin. Gears and bearing surfaces are often made this way, so the face resists wear while the body absorbs shock. A file skates on them. A Rockwell C test on the surface may read high, or it may punch through a thin case and report a blend of case and core. That is why ASTM International and ASM International both describe lighter, superficial Rockwell scales for thin layers. But the case depth must be measured on a cross-section.

{{steps: Hardness traverse | Cut through the part | Mount and polish the section | Make a row of small indents inward | >Plot hardness against depth}}
The method is called a hardness traverse. Cut through the part. Mount and polish the section. Make a row of small indents inward from the edge, using a Vickers or Knoop microindentation tester, which ASTM International covers in standard E384. Each indent is measured under a microscope by its diagonals rather than its depth. Plot hardness against depth, and the curve shows the hard case, the transition zone, and the softer core. The cost is obvious: the part is destroyed. That is the trade at the centre of this subject. The more you want to know, the more of the steel you usually have to cut.

### Only the microstructure shows how the hardness got there

{{chain: Microstructure check | polish the section | etch it in nital | examine under a microscope | >martensite confirms a quench}}
A hardness number tells you how hard. It does not tell you why. Cold working can raise hardness, and so can certain alloying additions. To confirm that steel was hardened by quenching, metallographers polish the section, etch it in nital, a dilute solution of nitric acid in alcohol, and examine under a microscope. Martensite appears as fine needles or laths, distinct from the layered plates of pearlite found in slowly cooled steel. When the microscope and the hardness traverse agree, the case is strong: martensite confirms a quench, and the numbers show how complete it was.

### What to notice in the edit

{{checklist: Strong evidence of hardening | +a calibrated Rockwell reading | +a hardness traverse | +martensite under the microscope | -a colour | -a magnet}}
As you watch, notice where the confidence comes from. Each claim of hardness in this episode rests on an instrument with a known reference: a calibrated Rockwell reading, a hardness traverse, martensite under the microscope. The weak signals appear on screen too, and they are shown as weak: a colour, a magnet, the ring of a struck bar. The file sits in between, useful and fast, but only as good as the hand holding it and the surface beneath it. When a diagram shows a number, it is a number the narration has spoken, beside the body that publishes the method.

### Evidence limit

{{text}}
This evidence has firm edges. A hardness reading is a property at one spot. It does not establish toughness, and a part can be very hard and still crack under impact if it was never tempered. It does not establish uniformity across a large part without many readings. Conversions between scales are approximate and specific to classes of material. And the destructive tests that answer the deepest questions, the traverse and the microstructure, are usually done on a sample or a sacrificed part, not on the one in your hand. For that part, you are inferring from a process that was controlled and checked, not measuring it directly.

### Closing

{{ambient}}
So the honest answer comes in layers. A file tells you the surface resists. A calibrated indenter tells you how much. A polished, etched section tells you why. Steel keeps its history on the inside, and the only way to read it is to press, to measure, and sometimes to cut.

## Editorial gate

*What this episode does that a template would not. Every line below is a property the pipeline enforces at build time — see V36 in `loop/validate.py`. It records no step a human still owes.*

- Humanized cold open: PRESENT
- First-person producer observation: FROM POV BANK (pov-103)
- Evidence uncertainty or limitation: COMPLETE
- Structural variation: an evidence ladder climbing from touch (file) to calibrated indentation to destructive sectioning, with a myth (the magnet) cut in at the midpoint
- Number-level source audit: COMPLETE

## Chapters

- 00:00 Cold open
- 00:45 Title card
- 00:50 Hardening changes the inside, so the outside barely tells you
- 02:30 A file gives a fast answer that can mislead
- 03:45 Producer POV
- 03:55 The Rockwell number is a depth, not the size of the dent
- 05:40 A hardness number is only as good as its calibration
- 06:55 A magnet answers a different question
- 08:15 A hard surface does not prove a hard core
- 09:45 Only the microstructure shows how the hardness got there
- 10:25 What to notice in the edit
- 11:05 Evidence limit
- 11:50 Closing

## Sources

- ASTM International: home page, publisher of standards E18 (Rockwell hardness), E140 (hardness conversion tables) and E384 (microindentation hardness) — https://www.astm.org/
- ASM International: home page, heat treating and metallography references — https://www.asminternational.org/
- NIST: home page, national measurement laboratory and source of Rockwell hardness standard reference blocks — https://www.nist.gov/
- MIT Department of Materials Science and Engineering: home page — https://dmse.mit.edu/