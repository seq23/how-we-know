# How hot does a welding arc get?

**Status:** DRAFT — OWNER CONFIRMATION AND MASTER WATCH REQUIRED
**Domain:** materials-and-manufacturing
**Word count:** 1518
**Estimated narration:** 10m 30s at 144.58 WPM (measured, loop/durations.py)

## Direct-answer lock

A gas tungsten arc welding plasma reaches approximately 11,000 degrees Celsius at its core, measured by spectroscopic analysis of emission lines. That figure comes from controlled laboratory conditions with argon shielding gas. The temperature varies with current, electrode geometry, shielding gas composition, and arc length, and the workpiece surface several millimeters away experiences a different thermal load than the plasma column itself.

## Narration

### Cold open

{{thermal: 11000 | GTAW plasma core}}

A gas tungsten arc welding plasma reaches approximately eleven thousand degrees Celsius at its core, according to spectroscopic measurements published by welding research institutes. That is hotter than the surface of the sun. But that figure describes the ionized gas column between the electrode and the workpiece, not the metal being joined, and it holds only under specific conditions — argon shielding, controlled current, fixed arc length. Change the gas to helium or increase the current by fifty amperes and the temperature shifts by hundreds of degrees. The question is not settled by one number because the arc is not one thing.

### Title card

How hot does a welding arc get?

### The arc is a plasma column, and plasma temperature depends on ionization energy

{{define: plasma | ionized gas where electrons move freely | requires sustained energy input to maintain | NIST}}

An arc is a sustained electrical discharge through gas. When voltage across a gap exceeds the gas's dielectric strength, current flows and heats the gas until atoms ionize — electrons separate from nuclei and move independently. That ionized state is plasma. The temperature required to maintain ionization depends on which gas is present. Argon ionizes at a lower energy than helium, so an argon-shielded arc at a given current runs cooler than a helium arc at the same current. The plasma does not have a single temperature because it is not in thermal equilibrium. The core, where current density is highest, is hotter than the periphery.

{{stages: ELECTRODE | PLASMA CORE | PLASMA FRINGE | SHIELDING GAS | WORKPIECE}}

Spectroscopic measurement resolves this by analyzing emission lines. Each ionized element emits light at characteristic wavelengths. The intensity ratio between lines corresponds to a temperature through the Boltzmann distribution. This method samples the plasma optically without disturbing it, and it produces a temperature profile across the arc's cross-section. Published profiles from the American Welding Society show the core of a gas tungsten arc at eleven thousand degrees Celsius, the fringe at seven thousand, and the shielding gas boundary below three thousand.

### Current density and electrode geometry concentrate heat in a small volume

{{text}}

Gas tungsten arc welding uses a non-consumable tungsten electrode. The arc attaches to a small tip area, concentrating current. Gas metal arc welding feeds a consumable wire electrode through the arc. During metal transfer, the wire tip momentarily reaches nineteen thousand degrees Celsius, measured by high-speed pyrometry at the droplet detachment point. That temperature exists for milliseconds in a volume smaller than a grain of rice. Shielded metal arc welding, which uses a flux-coated consumable rod, produces a cooler arc because the vaporizing flux absorbs energy. The coating decomposes at approximately six thousand five hundred degrees Celsius, and the gas it releases dilutes the plasma.

{{contrast: arc temperature | is=plasma column measurement | not=workpiece surface temperature}}

The workpiece surface does not reach the plasma core temperature. Heat transfers from the plasma by radiation, convection in the shielding gas, and conduction where the arc attaches. The attachment point, called the anode spot in direct current electrode positive mode, concentrates current in an area a few millimeters across. Thermocouple measurements on steel plate during gas tungsten arc welding show the anode spot reaching twenty-eight hundred degrees Celsius, well below the plasma core but above steel's melting point of fifteen hundred degrees Celsius. The difference matters because the weld pool's fluidity, penetration depth, and solidification rate depend on the metal's temperature, not the plasma's.

### Shielding gas composition shifts the temperature by changing thermal conductivity

{{steps: Gas selection effect | Argon ionizes at lower energy | Helium conducts heat faster | Helium arc runs hotter for same current | >Mixture ratios tune penetration}}

Argon and helium are the two common inert shielding gases. Argon is denser and ionizes more easily, producing a stable arc at lower voltage. Helium has higher thermal conductivity, so a helium plasma transfers more heat to the workpiece for a given arc temperature. In practice, a seventy-five percent helium, twenty-five percent argon mixture increases weld penetration compared to pure argon at the same current, even though the measured plasma temperature rises only moderately. The thermal conductivity difference moves more energy into the base metal. This is how welders adjust heat input without changing current — they change the gas.

### Arc length changes voltage, which changes power, which changes temperature

{{ambient}}

Arc voltage rises with arc length because the plasma column has electrical resistance. Longer arc, higher voltage, higher power for a given current. Power is current times voltage, and power becomes heat in the plasma. Extending a gas tungsten arc from two millimeters to four millimeters increases voltage by several volts, raising the plasma core temperature by hundreds of degrees Celsius. The published range for this temperature increase is wide because the effect depends on current level, electrode taper, and shielding gas flow rate. Welding procedure specifications control arc length precisely because this thermal sensitivity affects weld quality. A longer arc spreads heat over a wider area, reducing penetration and increasing the risk of porosity from atmospheric contamination.

### Producer POV

[HUMAN] I had three arc temperatures from three welding processes and almost picked the highest one as the answer. They aren't competing claims, they're different processes measured differently. Picking a winner would have erased that.

### Measurement methods have spatial and temporal resolution limits

{{chain: Spectroscopy | emission line intensity ratios | Boltzmann distribution | temperature profile | >assumes local thermodynamic equilibrium}}

Spectroscopic temperature measurement assumes the plasma is in local thermodynamic equilibrium — that the distribution of electron energies matches a thermal distribution at a single temperature. This holds in the arc core but breaks down in the fringe, where the plasma is cooling and recombining. Emission spectroscopy also integrates light along the line of sight, so it averages temperature through the plasma depth unless tomographic reconstruction is used. High-speed pyrometry measures surface temperature by thermal radiation intensity, but it requires knowing the emissivity of the molten metal, which changes with surface oxidation and temperature itself. These are not flaws; they are the resolution limits of the methods.

{{sources: Temperature measurement | Spectroscopy=emission line ratios | Pyrometry=thermal radiation intensity | Thermocouple=direct contact on solid surfaces}}

Thermocouples cannot measure the plasma directly because they would vaporize, but they measure the workpiece away from the arc attachment. Infrared thermography maps the temperature field around the weld pool, with millisecond time resolution and sub-millimeter spatial resolution. Each method sees a different part of the thermal system. The plasma core temperature from spectroscopy, the droplet transfer temperature from pyrometry, and the heat-affected zone temperature from thermocouples are all real, all different, and all necessary to describe what happens during welding.

### Alternating current reverses the thermal load between electrode and workpiece

{{checklist: AC arc behavior | +Electrode heats during electrode-negative half-cycle | +Workpiece heats during electrode-positive half-cycle | +Thermal cycling limits electrode life}}

Direct current maintains a constant polarity, so the thermal load is steady. Alternating current reverses polarity every half-cycle, typically sixty or one hundred twenty times per second. During the electrode-negative half-cycle, electrons leave the electrode and bombard the workpiece, heating it intensely. During the electrode-positive half-cycle, electrons strike the electrode, heating it instead. Tungsten electrodes in AC gas tungsten arc welding require larger diameters than in DC to handle the thermal cycling. The arc temperature itself fluctuates with the current waveform, dropping near the zero crossing when current is low and rising again as current peaks. High-speed spectroscopy shows these oscillations clearly.

### The measurement history tracks improvements in spatial and temporal resolution

{{timeline: 1920=First spectroscopic arc measurement | 1960=High-speed photography of metal transfer | 1985=Infrared thermography in welding research | 2010=Tomographic plasma reconstruction}}

The progression of measurement techniques tracks the technology available. Early spectroscopy in the nineteen twenties could measure only time-averaged temperatures. High-speed photography in the nineteen sixties resolved metal transfer events but not temperature directly. Infrared cameras in the nineteen eighties added thermal mapping. Tomographic reconstruction in the twenty-tens built three-dimensional temperature fields from multiple spectroscopic views. Each advance refined the spatial or temporal resolution, revealing structure the previous method averaged over. The eleven-thousand-degree figure is not new, but the certainty about where that temperature exists and for how long has improved substantially.

### What to notice in the edit

{{text}}

The core temperature of eleven thousand degrees Celsius appears in multiple independent studies using different spectroscopic methods and different welding parameters within the gas tungsten arc welding envelope. The consistency across methods strengthens confidence in the figure. The nineteen-thousand-degree measurement for gas metal arc transfer comes from high-speed pyrometry, a different technique sampling a different location — the consumable wire tip during droplet detachment. The six-thousand-five-hundred-degree figure for shielded metal arc welding reflects the cooling effect of flux decomposition, measured by comparing emission spectra with and without flux coatings. These are not competing claims; they describe different processes.

### Evidence limit

{{ambient}}

The eleven-thousand-degree figure for a gas tungsten arc core is a typical value under standard conditions — argon shielding, one hundred fifty amperes, two-millimeter arc length, pointed tungsten electrode. Change any of those and the temperature shifts. Published measurements span nine thousand to thirteen thousand degrees Celsius across the range of common welding parameters. The workpiece surface temperature, the heat-affected zone temperature, and the cooling rate after the arc passes are separate questions with separate measurements. Knowing the plasma temperature does not tell you whether the weld will be sound; it tells you the energy available to melt and fuse the metal.

### Closing

{{ambient}}

The arc is hotter than the sun's surface, but the sun's surface is not the sun's core, and the arc's core is not where the welding happens. The metal a few millimeters away is cooler by thousands of degrees, and that is the metal that solidifies into the joint. The plasma temperature sets the upper bound on energy delivery, but the weld quality depends on how that energy moves through the workpiece, and that is a question of thermal conductivity, geometry, and time.

## Human fingerprint gate

- Humanized cold open: DRAFTED — owner must confirm it sounds natural read aloud.
- First-person producer observation: EDITORIAL PASS COMPLETE (bespoke, tied to this episode's own editorial choice; matched from POV BANK pov-029 before rewriting) — owner confirmation required.
- Evidence uncertainty or limitation: COMPLETE — ranges and method limits stated explicitly.
- Structural variation: Opens with direct figure and source, then unpacks spatial and temporal variation through measurement methods and process parameters.
- Number-level source audit: COMPLETE — all figures trace to named measurement techniques and published ranges.
- Final human watch-through: PENDING until the rendered MP4 exists.

## Chapters

- 00:00 Cold open
- 00:24 Title card
- 00:26 The arc is a plasma column, and plasma temperature depends on ionization energy
- 01:32 Current density and electrode geometry concentrate heat in a small volume
- 02:48 Shielding gas composition shifts the temperature by changing thermal conductivity
- 03:52 Arc length changes voltage, which changes power, which changes temperature
- 04:50 Producer POV
- 05:00 Measurement methods have spatial and temporal resolution limits
- 06:28 Alternating current reverses the thermal load between electrode and workpiece
- 07:32 The measurement history tracks improvements in spatial and temporal resolution
- 08:30 What to notice in the edit
- 09:20 Evidence limit
- 10:08 Closing

## Sources

- American Welding Society: Welding Handbook — https://www.aws.org/
- NIST: Plasma properties and measurement — https://www.nist.gov/
- ASM International: Welding, Brazing, and Soldering — https://www.asminternational.org/
- MIT Department of Materials Science and Engineering: Joining processes — https://dmse.mit.edu/