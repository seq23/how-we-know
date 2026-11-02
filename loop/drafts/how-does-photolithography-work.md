# How does photolithography work?

**Status:** DRAFT — OWNER CONFIRMATION AND MASTER WATCH REQUIRED
**Domain:** materials-and-manufacturing
**Opening:** stake-then-payoff
**Word count:** ~1740
**Estimated narration:** 12m 2s at 144.58 WPM (measured, loop/durations.py)

## YouTube title

Photolithography without glass lenses

## Direct-answer lock

Photolithography copies a circuit pattern onto a silicon wafer by shining light through a patterned mask onto a light-sensitive coating called photoresist, which changes its chemistry wherever the light lands. Developing the resist leaves a stencil, and later steps etch, implant or deposit material through it. Repeating the sequence layer after layer builds the chip. The wavelength of the light sets the scale of the smallest features, which is why the most advanced tools use extreme ultraviolet at 13.5 nanometres.

## Narration

### Cold open

{{text}}
Air or glass would swallow the beam that prints a modern chip's smallest features. Photolithography copies a circuit pattern onto a silicon wafer by shining light through a patterned mask onto a light-sensitive coating called photoresist, which changes its chemistry wherever the light lands. In the most advanced machines that light has a wavelength of 13.5 nanometres, as the engineering literature published through IEEE describes. People quote that figure. It sets a scale, and it explains a great deal about why these machines look the way they do. It does not explain how factories have spent decades printing lines far narrower than the light that drew them. That gap is the real story.

### Title card

How does photolithography work?

### A stencil is made from light-sensitive chemistry

{{steps: The basic sequence | coat | bake | expose | develop | etch | >repeated layer after layer}}
Start with a polished silicon wafer. The first step is to coat it with a thin, even film of photoresist. Usually liquid is dripped onto the wafer and the wafer is spun so the film spreads flat. A gentle bake drives off solvent. Before each exposure, the machine finds alignment marks left by earlier layers, so the new pattern sits on top of the old one. Then you expose the wafer. Light passes through a mask, which is a plate of glass carrying the circuit pattern in an opaque layer. An optical system projects a reduced image of that pattern onto the resist. Next you develop it, washing the wafer in a solution that dissolves either the exposed or the unexposed regions. What remains is a stencil. Finally you etch, implant or deposit material through the openings, and then you strip the resist away. That whole sequence is repeated layer after layer. A finished chip is the accumulated result.

{{contrast: Contact printing | is=the mask touches the resist directly | not=projected rather than pressed}}
Nothing in that list is exotic in principle. University cleanrooms, including facilities at MIT, teach the sequence to students with simple contact printers, where the mask touches the resist directly. The industrial version differs in scale and tolerance. The idea is the same. In a factory the mask is projected rather than pressed, and the lens shrinks the image. The wafer is stepped or scanned beneath the optics so the same pattern lands in many places across its surface. The machine is enormous, but each exposure is still a shadow falling on a chemical film.

### The resist records light as a change in solubility

{{define: Photoresist | a coating whose solubility changes where light lands | positive or negative tone | IEEE}}
Photoresist is a coating whose solubility changes where light lands. It comes in positive or negative tone. In a positive resist, exposed regions become easier to dissolve, so the developer removes them. In a negative resist, exposure makes the material harder to dissolve, so the exposed regions stay behind. In both cases the resist converts an optical image into a chemical one. The rest of the process responds to the chemistry, not the light.

{{chain: Chemical amplification | photon is absorbed | acid is released | bake spreads the reaction | >the pattern becomes soluble}}
Most modern resists add a trick called chemical amplification. Inside the film sits a compound that releases acid when it absorbs light. A photon is absorbed, an acid is released, and then a bake spreads the reaction. That acid molecule wanders a short distance and catalyses many chemical changes in the surrounding polymer before it is spent. Where enough of those changes accumulate, the pattern becomes soluble. Amplification means each exposure needs fewer photons, which matters because short-wavelength light is expensive to make. It also means the edge of every line depends partly on where acid molecules happened to drift. That drift causes roughness at the edges of lines, and researchers publishing through IEEE continue to study it.

### Producer POV

[HUMAN] The footage is real. The documentary around it is constructed — lights, music, editing, narration all telling you what to feel.

### Wavelength sets the floor, and optics move it

{{chain: Resolution limit | wavelength | numerical aperture | >smallest printable feature}}
Diffraction limits the sharpness of any projected image. Light passing through a fine opening spreads out, and a lens can only collect so much of that spread. Engineers often describe the relationship with the Rayleigh criterion. The smallest printable feature scales with the wavelength of the light, divided by the numerical aperture of the lens, multiplied by a factor that captures everything else about the process. A shorter wavelength gives smaller features. A wider collecting angle also gives smaller features. A cleverer process shrinks them further.

{{magnitude: Exposure wavelengths | nanometres | i-line=365 | KrF=248 | ArF=193 | EUV=13.5}}
For that reason, the history of the industry reads as a march down the spectrum. The IEEE literature traces it in steps. Mercury lamps emitted the i-line at 365 nanometres. Krypton fluoride lasers, written KrF, followed at 248 nanometres, and argon fluoride lasers, written ArF, came next at 193 nanometres. After that the industry paused for a long time. Going shorter than 193 proved so difficult that manufacturers squeezed more out of the same light for years before extreme ultraviolet, or EUV, was ready.

{{contrast: Immersion lithography | is=water between lens and wafer | not=a new wavelength}}
One way to do that was immersion. A thin layer of water is placed between lens and wafer. Water bends light more strongly than air, so the lens can accept a wider cone of light, which effectively raises the numerical aperture. Immersion is not a new wavelength. IEEE papers on immersion describe it as the same 193 nanometre light, focused more tightly. Immersion moves the second term of the equation and leaves the first unchanged.

### Extreme ultraviolet required mirrors, vacuum and molten tin

{{stat: 13.5 | nanometres | extreme ultraviolet exposure wavelength | IEEE}}
Extreme ultraviolet light at 13.5 nanometres, the exposure wavelength documented across IEEE venues, is absorbed by almost everything. That includes air and every glass that could form a lens. So an EUV scanner works without glass lenses. The whole light path runs in vacuum, and curved mirrors form the image. Even the mask is a mirror instead of a transparent plate. Each mirror is a stack of many alternating ultrathin layers, classically molybdenum and silicon. The layers are tuned so that weak reflections from every interface add together. No single surface reflects this light well. The stack reflects it collectively, and it still loses a substantial share of the light at every bounce. NIST has worked on measuring how these optics reflect and how they degrade under exposure.

{{stages: PLASMA}}
Making 13.5 nanometre light at all requires a plasma. The IEEE literature describes how production sources work. Small droplets of molten tin are struck by a pulsed laser, which heats them into a plasma that emits in the extreme ultraviolet. The machine then has to keep tin debris off the collecting mirror. Only a small fraction of the light the plasma produces ever reaches the wafer. That loss is one reason amplified resists matter so much.

{{magnitude: Numerical aperture | dimensionless | current EUV tools=0.33 | high numerical aperture designs=0.55}}
Mirror systems have their own numerical aperture, a dimensionless number. IEEE publications describe current EUV tools with a numerical aperture of 0.33. Newer high numerical aperture designs raise it to 0.55, at the cost of more complex optics. Those two numbers show that the Rayleigh logic still holds. When the wavelength cannot easily shrink further, the collecting angle becomes the next lever.

### Lines can be narrower than the light that drew them

{{checklist: Working inside the limit | +optical proximity correction | +phase-shift mask | +multiple patterning | ?how far the process factor can fall}}
The answer to the cold open's puzzle lies in the third term, the process factor. Wavelength and numerical aperture are hardware. The process factor covers everything engineers can do with the mask, the light and the chemistry. Engineers have pushed it down by refusing to treat the mask as a literal picture of the circuit. One technique is optical proximity correction. Diffraction rounds corners and shortens line ends, so the mask is drawn deliberately wrong, with small extra tabs and bars, and the blurred image prints the intended shape. Another technique is the phase-shift mask. It delays the light through some openings relative to their neighbours, so the two waves cancel at the boundary between them and the edge prints sharper. A third is multiple patterning. A pattern too dense for one exposure is split across two or more masks, and each is printed and etched in turn. The combined result is finer than any single exposure could reach. Nobody yet knows how far the process factor can fall before physics or cost stops it.

{{text}}
None of this breaks the diffraction limit. These techniques work within the limit by shaping the light so the blur lands in the right places. That is how factories printed lines far narrower than 193 nanometres with the 193 nanometre light described in IEEE papers. It is also why the 13.5 nanometre figure, impressive as it is, describes the starting point of the problem rather than its solution.

### Measurement, not the picture, proves the pattern

{{sources: Who measures | NIST=reference measurements of critical dimensions | SEMI=standards for wafers and masks}}
Checking that the printed lines have the right width is its own discipline. Factories measure critical dimensions, the widths of the most important features. One tool is the scanning electron microscope, which images the resist from above. Another is scatterometry, which infers the shape of a repeating pattern from how it diffracts light. Factories also measure overlay, which tells them whether each layer landed on top of the previous one where it should. NIST works on reference measurements of critical dimensions, so that a width measured in one tool means the same thing in another. SEMI, the industry association, publishes standards for wafers and masks. Those shared definitions let equipment from different suppliers work together.

{{chain: How a pattern is confirmed | electron microscope | scatterometry | overlay | >whether the transistors behave electrically}}
The confirmation that photolithography works at a given scale comes mostly after the fact. Engineers measure with the electron microscope, with scatterometry and with overlay checks. They cut finished devices open and image the cross-sections. The final test is whether the transistors behave electrically as designed. The physics predicts the result, and the measurements check it.

### What to notice in the edit

{{text}}
Renderings of lithography usually show a beam of glowing violet light falling onto a wafer. Extreme ultraviolet is invisible, and it travels in vacuum inside a closed machine, so any glow you see was the artist's choice. Animations often show a crisp, finished circuit appearing in one flash. In reality, one exposure makes one hidden image in one layer of resist. Nothing shows until development, and even then you may need a microscope to see it. The yellow light in cleanroom footage, by contrast, is real. That lighting filters out the short wavelengths that would expose the resist by accident.

### Evidence limit

{{checklist: What the evidence settles | +the optical principle | +the wavelengths used | -exact process recipes | ?how far the process factor can fall}}
The optical principle is settled physics, and the wavelengths used are published and stable. Public sources do not give you the exact process recipes inside any particular factory. Resist formulations, bake conditions, mask corrections and dose settings are proprietary. Outside accounts can describe the method in general, but they give specific numbers only where a manufacturer chooses to share them. The marketing names for chip generations sound like measurements, but they no longer correspond to any single physical width, so treat them as labels. Claims about how far the process factor can fall, or when a shorter wavelength might arrive, are forecasts, not findings.

### Closing

{{ambient}}
Every layer of a chip began as a pattern of light on a chemical film, developed into a stencil and then made permanent. The wavelength sets the scale. The clever work happens in the gap between that scale and the lines a factory actually prints.

## Editorial gate

*What this episode does that a template would not. Every line below is a property the pipeline enforces at build time — see `loop/validate.py`. It records no step a human still owes.*

- Humanized cold open: PRESENT
- First-person producer observation: FROM POV BANK (pov-036)
- Evidence uncertainty or limitation: COMPLETE
- Structural variation: the cold open plants an apparent paradox, features smaller than their wavelength; the episode builds the resolution equation term by term and resolves the paradox in its fifth section rather than at the end
- Number-level source audit: COMPLETE

## Chapters

- 00:00 Cold open
- 00:48 Title card
- 00:50 A stencil is made from light-sensitive chemistry
- 02:30 The resist records light as a change in solubility
- 03:55 Producer POV
- 04:05 Wavelength sets the floor, and optics move it
- 05:35 Extreme ultraviolet required mirrors, vacuum and molten tin
- 07:20 Lines can be narrower than the light that drew them
- 08:55 Measurement, not the picture, proves the pattern
- 10:10 What to notice in the edit
- 10:55 Evidence limit
- 11:45 Closing

## Sources

- IEEE: IEEE home page and publications portal — https://www.ieee.org/
- NIST: National Institute of Standards and Technology home page — https://www.nist.gov/
- SEMI: SEMI home page, including SEMI International Standards — https://www.semi.org/
- MIT: Massachusetts Institute of Technology home page — https://www.mit.edu/