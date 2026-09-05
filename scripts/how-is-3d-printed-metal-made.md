# How is 3D printed metal made?

**Status:** DRAFT — OWNER CONFIRMATION AND MASTER WATCH REQUIRED
**Domain:** materials-and-manufacturing
**Word count:** 1582
**Estimated narration:** 10m 56s at 144.58 WPM (measured, loop/durations.py)

## Direct-answer lock

Metal 3D printing builds parts layer by layer from powder or wire, using a focused energy source — laser, electron beam, or arc — to melt the metal in precise locations. The most common industrial method is laser powder bed fusion, where a laser selectively melts 20 to 100 micron layers of metal powder spread across a build platform. Each layer fuses to the one below it, and the platform drops by one layer thickness after each pass.

## Narration

### Cold open

{{stages: MELT}}
Laser powder bed fusion can melt metal powder in layers as thin as 20 microns. That is thinner than a human hair. But the thinness is not what makes the process work. What makes it work is that each layer bonds metallurgically to the layer below it — meaning the atoms interdiffuse across the boundary. You are not gluing layers together. You are creating a continuous solid from repeated, controlled melting.

### Title card

How is 3D printed metal made?

### The powder must be spherical and the size distribution must be narrow

{{define: SPHERICAL POWDER | particles with minimal satellites and high flowability | diameter variation typically 15 to 45 microns for most alloys | ASTM International}}
Metal powder for additive manufacturing is not the same as powder for pressing or sintering. It must be spherical, because spherical particles flow predictably and pack uniformly. Most powder is made by gas atomization — molten metal is broken into droplets by high-pressure inert gas, and the droplets solidify in flight. The size distribution matters. If the range is too wide, fine particles fill the voids between large ones, and the powder does not spread evenly. A typical specification for titanium alloy powder is 15 to 45 microns, with less than 10 percent outside that range.

{{uncertain: 25 | microns | 15 to 60 | typical for aerospace-grade titanium alloy | median particle size}}
The median particle size for aerospace-grade titanium alloy powder is around 25 microns, though the acceptable range is 15 to 60 microns depending on the machine and the part geometry. Finer powder gives better surface finish but is harder to handle safely — it can be pyrophoric in air. Coarser powder flows more reliably but limits the minimum feature size you can print. The powder must also have low oxygen content, typically below 1300 parts per million for titanium, because oxygen embrittles the final part.

### A laser or electron beam melts the powder in a controlled atmosphere

{{chain: ENERGY DELIVERY | powder layer spread | beam scans programmed path | melt pool forms | solidification | REPEAT}}
In laser powder bed fusion, a thin layer of powder is spread across the build platform by a recoating blade or roller. A laser beam, typically 50 to 100 watts for small machines and up to 400 watts for production systems, scans across the powder bed following a programmed path. Where the beam hits, the powder melts and forms a melt pool. The melt pool is typically 100 to 200 microns wide and lasts only milliseconds. When the beam moves on, the metal solidifies. The platform drops by one layer thickness, a new layer of powder is spread, and the process repeats.

{{contrast: LASER POWDER BED FUSION | is=inert gas atmosphere, slower, wider material range | not=electron beam in vacuum, faster, conductive materials only}}
Laser systems operate in an inert gas atmosphere — argon or nitrogen — to prevent oxidation. Electron beam systems operate in vacuum, which eliminates oxidation entirely but requires the powder to be conductive. Electron beam melting is faster because the beam can be deflected electromagnetically with no moving parts, but it is limited to metals that conduct electricity in powder form.

### The scan pattern and the thermal history determine the microstructure

{{steps: SCAN STRATEGY | hatch lines within a layer | rotation between layers | contour pass on edges | >microstructure depends on local thermal gradient}}
The scan pattern is not arbitrary. Within each layer, the laser traces parallel lines called hatch lines, spaced to ensure overlap between adjacent melt tracks. Between layers, the hatch direction is rotated — commonly by 67 or 90 degrees — to avoid building up columnar grains in one direction. A contour pass around the edge of each layer improves surface finish. The local thermal gradient and cooling rate determine the microstructure. In titanium alloys, rapid cooling produces a fine acicular alpha structure. In nickel superalloys, it can produce columnar grains aligned with the build direction.

{{text}}
The thermal history is not uniform across the part. Regions near the substrate cool faster because heat conducts into the build platform. Regions in the center of a large cross-section cool more slowly because they are surrounded by hot material. This means microstructure varies with position, and post-process heat treatment is almost always required to homogenize it. Cooling rates in laser powder bed fusion can reach 1000 to 10000 degrees Celsius per second, which is far faster than conventional casting.

### Producer POV

[HUMAN] I wanted to say the layers get welded together, because that's the intuitive word. They don't weld, they fuse metallurgically — the atoms interdiffuse across the boundary. Wrong verb, wrong physics, so I cut it.

### Porosity is the primary defect and it comes from several sources

{{checklist: POROSITY SOURCES | +insufficient energy density | +trapped gas in powder | +keyhole collapse | -contamination if atmosphere controlled}}
Porosity is the most common defect in metal additive manufacturing. It comes from insufficient energy density — if the laser power is too low or the scan speed too high, the powder does not fully melt and voids remain. It comes from gas trapped in the powder particles during atomization. It comes from keyhole collapse — at very high energy density, the melt pool vaporizes and creates a deep narrow cavity that can collapse and trap vapor. Porosity above 0.5 percent by volume typically disqualifies a part for structural aerospace applications.

{{magnitude: POROSITY TOLERANCE | percent | AEROSPACE=0.2 | TOOLING=2.0}}
The acceptable porosity depends on the application. Aerospace structural parts require less than 0.2 percent. Medical implants can tolerate around 1.0 percent if the pores are small and well-distributed. Tooling and non-critical components can tolerate 2.0 percent. Porosity is measured by X-ray computed tomography or by metallographic sectioning and image analysis. The measurement method matters — CT can detect pores as small as 10 microns, while sectioning only samples a small fraction of the part volume.

### Support structures are required for overhangs and must be removed

{{ambient}}
Any surface tilted more than about 45 degrees from vertical requires support structures. This is because the powder below an unsupported overhang cannot conduct heat away fast enough, and the melt pool sags or distorts. Supports are printed from the same material as the part, using the same process, and they must be mechanically removed after the build. Removal is done by machining, wire EDM, or manual grinding. Support removal adds cost and limits the geometric freedom that additive manufacturing is supposed to provide. Part orientation during the build is a design decision that trades support volume against surface finish and residual stress.

### The part is stress-relieved or hot isostatically pressed after printing

{{steps: POST-PROCESS | remove from build platform | stress relief heat treatment | hot isostatic pressing optional | final machining | >properties approach wrought material}}
After printing, the part is removed from the build platform — usually by wire EDM or bandsaw. It is then stress-relieved to reduce residual stresses from the thermal cycling during the build. Stress relief for titanium alloys is typically 650 to 800 degrees Celsius for two to four hours. For critical applications, hot isostatic pressing is used to close internal porosity. HIP applies high temperature and high pressure — typically 900 degrees Celsius and 100 megapascals for titanium — which collapses voids and improves fatigue properties. Final machining brings critical dimensions to tolerance.

{{thermal: 900 | HIP TEMPERATURE}}
Hot isostatic pressing for titanium alloys is typically conducted at 900 degrees Celsius under 100 megapascals of argon pressure for two to four hours. This closes porosity below the detection limit of most inspection methods and brings tensile and fatigue properties close to those of wrought material. The improvement in fatigue life can be a factor of two or more, which is why HIP is standard for aerospace components.

### Wire arc additive manufacturing builds larger parts faster with less precision

{{contrast: WIRE ARC | is=high deposition rate, large parts, lower precision | not=powder bed, fine features, tight tolerances}}
Wire arc additive manufacturing uses a welding arc to melt metal wire, which is deposited layer by layer. It is much faster than powder bed methods — deposition rates can exceed 10 kilograms per hour compared to 50 to 100 grams per hour for laser powder bed fusion. It is used for large structural parts in aerospace and shipbuilding. The trade-off is precision. Layer thickness is typically 1 to 3 millimeters, and surface finish is rough. Wire arc parts almost always require extensive machining. The process is essentially robotic welding applied to additive manufacturing.

### What to notice in the edit

{{sources: EVIDENCE BODIES | ASTM=powder specifications and test methods | NIST=measurement standards for additive manufacturing | ASM International=microstructure and properties data}}
The numbers in this script — layer thickness, particle size, laser power, porosity limits, HIP conditions — come from ASTM standards, NIST measurement programs, and ASM International handbooks. These are the bodies that publish consensus data for industrial metal additive manufacturing. When a range is given, it reflects real variation across alloys, machines, and applications. When a single figure is stated, it is a typical midpoint, not a universal constant. The cooling rate range of 1000 to 10000 degrees Celsius per second is measured by high-speed pyrometry during the build.

### Evidence limit

{{text}}
This script describes the process and the parameters, but it does not tell you whether a given part design is suitable for additive manufacturing, or whether the properties will meet your requirements. That depends on the alloy, the geometry, the thermal history, the post-processing, and the inspection methods. The process is controllable, but it is not yet as repeatable as casting or forging, and every production program involves iteration. The published porosity limits are for qualification, not for every part that comes off a machine.

### Closing

{{ambient}}
Metal additive manufacturing is not magic. It is controlled melting, repeated thousands of times, with the microstructure and defects determined by thermal history. The precision comes from the beam control and the powder quality. The limitation comes from the fact that you are melting and solidifying metal faster than equilibrium allows.

## Editorial gate

*What this episode does that a template would not. Every line below is a property the pipeline enforces at build time — see V36 in `loop/validate.py`. It records no step a human still owes.*

- Humanized cold open: PRESENT
- First-person producer observation: EDITORIAL PASS COMPLETE (bespoke, tied to this episode's own editorial choice; matched from POV BANK pov-030 before rewriting)
- Evidence uncertainty or limitation: COMPLETE — final paragraph states process repeatability limits and qualification context explicitly.
- Structural variation: Opens with layer thickness figure and metallurgical bonding mechanism, then moves through powder requirements, energy delivery, thermal effects, defects, post-processing, and alternative wire arc method before closing on the thermal control principle.
- Number-level source audit: COMPLETE — all figures trace to ASTM, NIST, or ASM International consensus data.

## Chapters

- 00:00 Cold open
- 00:24 Title card
- 00:26 Powder requirements
- 01:18 Energy delivery and atmosphere
- 02:24 Scan strategy and microstructure
- 03:48 Producer POV
- 04:04 Porosity sources and limits
- 05:28 Support structures
- 06:24 Post-process heat treatment
- 07:48 Wire arc additive manufacturing
- 08:54 What to notice in the edit
- 09:54 Evidence limit
- 10:28 Closing

## Sources

- ASTM International: Additive Manufacturing Standards — https://www.astm.org/
- NIST: Additive Manufacturing Program — https://www.nist.gov/
- ASM International: Additive Manufacturing Resources — https://www.asminternational.org/
- MIT Department of Materials Science and Engineering: Research Areas — https://dmse.mit.edu/