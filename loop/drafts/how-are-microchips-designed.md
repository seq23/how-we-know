# How are microchips designed?

**Status:** DRAFT — OWNER CONFIRMATION AND MASTER WATCH REQUIRED
**Domain:** materials-and-manufacturing
**Opening:** cold-open-payoff
**Word count:** ~1900
**Estimated narration:** 13m 8s at 144.58 WPM (measured, loop/durations.py)

## YouTube title

Microchips are designed as code before silicon exists — and how we know

## Direct-answer lock

Microchips are designed almost entirely as software. Engineers describe a circuit's behaviour in a hardware description language. Automated tools then turn that description into logic gates, and then into the physical geometry of billions of transistors. Simulation, formal proof and rule checks test the result before anything is manufactured. The Intel 4004 of 1971 held about 2,300 transistors and was laid out by hand, but modern chips are far too large for that, so the answer is the automated design flow itself rather than a drawing board.

## Narration

### Cold open

{{stat: 2,300 | transistors | Intel 4004, laid out by hand | IEEE}}
Microchips are designed almost entirely as software. Engineers write down what a circuit should do in a hardware description language. Automated tools translate that description into logic gates, then into the physical geometry of billions of transistors, and simulation checks all of it before anything is manufactured. The past makes the point. IEEE's histories record that the Intel 4004, released in 1971, held about 2,300 transistors, and that it was laid out by hand. Nobody lays out billions by hand. So the interesting question is not who draws a modern chip. The question is how anyone can know that a design which has never physically existed will work on the day it finally does.

### Title card

How are microchips designed?

### A chip begins as a description of behaviour, not a picture

{{contrast: register-transfer level | is=a description of how data moves between registers on each tick of the clock | not=a drawing of transistors}}
The starting point is a specification. It sets out what the chip must compute, how fast, and within what power budget. From there, designers write at what is called the register-transfer level. A register is a small block of storage. The description says, in effect: on each tick of the clock, take the values in these registers, combine them this way, and store the result over there. So it is a description of how data moves between registers on each tick of the clock. It is not a drawing of transistors, and it does not say where anything sits on the silicon. That separation is deliberate. A person can reason about data moving between registers. A person cannot reason about billions of individual switches. The whole design method rests on letting humans work at the level where their judgement is reliable, and letting software handle the levels where it is not.

{{define: hardware description language | text that describes circuit behaviour and structure, which tools can simulate and synthesise | it is not a program that runs on a processor | IEEE}}
The text itself is written in a hardware description language. The two most widely known are Verilog and VHDL, and IEEE maintains both as formal standards. That matters for a practical reason. A description has to mean exactly the same thing to every tool that reads it, from different vendors, years apart. A hardware description language looks a little like ordinary programming code, but it is not a program that runs on a processor. Lines that appear one after another on the page may describe pieces of hardware that all operate at the same instant. This is the first place where intuition from software misleads people. The text describes structure and timing, and the same file serves two purposes. It can be simulated, to see what the circuit would do, and it can be synthesised, to build the circuit itself.

### Synthesis turns code into gates a factory already knows how to make

{{steps: From description to gates | register-transfer level | synthesis | standard cells | >timing constraints decide what counts as done}}
Synthesis is the step that converts the register-transfer level description into a netlist, which is a list of logic gates and the wires connecting them. The gates are not invented fresh for each chip. The manufacturer, called the foundry, supplies a library of standard cells. These are pre-designed, pre-measured building blocks such as basic logic gates and storage elements. Each one is characterised for how fast it switches and how much power it draws under that foundry's process. The synthesis tool's job is to find an arrangement of standard cells that does what the description says. There are usually many correct arrangements, and they differ in size, speed and power, so synthesis is really a search. The tool tries to satisfy goals the engineers have set, and the most important of those goals are timing constraints.

{{text}}
Timing constraints decide what counts as done. A clock signal sets the rhythm of the chip. Every signal has to travel from one register, through its gates, to the next register before the next tick arrives. If one path is too slow, the circuit computes the wrong answer whenever that path is exercised. Static timing analysis checks every such path mathematically, using the delays measured for each standard cell. It does not wait to see whether a simulation happens to trip over the slow one. This is one of the clearest examples of the design flow trading observation for exhaustive calculation.

### Placement and routing are optimisation problems handed to algorithms

{{chain: From netlist to geometry | placement | routing | parasitic extraction | >timing is checked again}}
A netlist says which gates connect to which. It says nothing about where they go. Placement assigns every standard cell a position on the die. Routing then draws the metal wires that join them, across many stacked layers of interconnect. Neither step is done by hand. Both are optimisation problems far too large to solve perfectly, so commercial tools use methods that find very good solutions rather than provably best ones. Once wires exist, they have real length, resistance and capacitance, and those properties slow signals down. A step called parasitic extraction estimates them from the geometry. Then timing is checked again with the new delays included. If the checks fail, engineers adjust the placement, the constraints or the design itself, and the loop repeats. Much of a chip's schedule is spent going round that loop.

{{sources: Who shaped the method | IEEE=standardises Verilog and VHDL | MIT=a course built on that method}}
This layered way of working has a history. In the late nineteen-seventies, Carver Mead and Lynn Conway set out a method that separated system design from the details of a particular fabrication process. It used simplified layout rules, so designers did not need to be device physicists. Lynn Conway taught a course at MIT built on that method, and the students' designs were gathered and fabricated together. Today IEEE standardises Verilog and VHDL, the languages at the top of the flow, so that tools from different companies agree. The point of this history is not who deserves credit. The point is that modern chip design is a deliberate stack of abstractions, each one checked against the one below it.

### Producer POV

[HUMAN] How do we know an animal behaves a certain way when we've seen it three times?

### Most of the work is proving the design is right

{{contrast: verification | is=evidence the design matches its specification | not=proof the chip will be manufactured correctly}}
That question came from the producer's notes on a different subject, animal behaviour, but it is exactly the right question here. A simulation is an observation. You feed the design a set of inputs, watch what it does, and compare that with what the specification says it should do. Seeing it behave correctly a few times proves very little. A chip has an astronomically large number of possible input sequences, and a fault might hide in one nobody tried. So verification teams do not just run tests. They also measure what their tests have exercised. Coverage metrics record which lines of the description ran, which conditions were hit, and which corner cases were reached. Verification produces evidence the design matches its specification. It is not proof the chip will be manufactured correctly, which is a separate problem handled later. Engineers across the industry describe verification as taking more effort than writing the design itself. How much more varies by project and by survey.

{{text}}
Where observation is not enough, there is a second tool. Formal verification uses mathematical methods to prove that a property holds for every possible input, not just the ones tried. For example, an engineer might state that two requests can never be granted the same resource at once. A formal tool either proves it, or returns a specific counterexample showing how it fails. Formal methods do not scale to everything on a large chip, so they are aimed at the parts where a hidden error would be most costly. Together, these give the honest answer to the producer's question. You watch many times, you measure how much you have watched, and where you can, you stop watching and prove.

### Physical rules are checked before any mask is made

{{checklist: Sign-off checks before tape-out | +design rule checking | +layout versus schematic | +timing sign-off | ?whether the foundry's models match real silicon}}
Before a design leaves the company, it goes through sign-off. Design rule checking compares the finished geometry against the foundry's rules. These include minimum widths, minimum spacings, and many subtler constraints that the manufacturing process requires. Layout versus schematic confirms that the shapes actually drawn form the same circuit as the netlist, with nothing shorted and nothing missing. Timing sign-off repeats the timing analysis across the full range of conditions the chip is specified for. That includes variations in temperature, supply voltage and the manufacturing process itself. Each of these is a mechanical check against a model. None of them can settle whether the foundry's models match real silicon. That depends on the foundry's measurements of its own process, and the design team largely has to trust them.

{{define: tape-out | the handoff of layout data to make photomasks | the end of design, not the end of uncertainty | SEMI}}
The handoff is still called tape-out, a name from the days when layout data left on magnetic tape. Today it is a file describing every polygon on every layer. The formats for that data are themselves standardised. SEMI, the semiconductor industry association, publishes a layout exchange standard called OASIS. The file goes to make photomasks, the stencils used to pattern each layer onto the wafer. Tape-out is the end of design, not the end of uncertainty. Masks are expensive, so a mistake found after this point costs far more to fix than one found in simulation. That cost is why so much of the flow exists.

### The first silicon is still an experiment

{{chain: Testing first silicon | wafers return | bring-up | post-silicon validation | >errata are documented}}
When the first wafers return, a phase called bring-up begins. Engineers power the chip on and check that its clocks run and its basic interfaces respond. Then they begin post-silicon validation, running real software and stress tests at full speed. This covers far more behaviour than any simulation could in the same time. Here the observational problem returns in a new form. Real silicon runs billions of cycles a second, so it explores behaviour quickly. But engineers can see far less of what is happening inside it than they could in a simulator. Designers often build in extra test and debug circuitry for exactly this reason. Problems found at this stage may be fixed with a revised set of masks, or worked around in software. Some are written up as errata, documents that tell customers which behaviours to avoid.

{{ambient}}
Underneath all of this sits measurement. Every one of these values began as a physical measurement of real structures on real wafers. That includes the delays in a standard cell library, the rules in a design rule check, and the variation a timing analysis allows for. This is why NIST works on the measurement science behind semiconductor manufacturing. A design flow that runs entirely in software is only as trustworthy as the measurements it was calibrated against.

### What to notice in the edit

{{timeline: 1965=Gordon Moore's paper | 1971=Intel 4004}}
In the edit, watch the scale change. In 1965, Gordon Moore published his observation that the number of components on a chip was growing on a steady schedule. IEEE has documented that pattern repeatedly since. By 1971 the Intel 4004 existed, still small enough to lay out by hand. Every diagram in this episode that shows code turning into gates, and gates into geometry, is showing the response to that growth. When a hand-drawn layout appears on screen, it is history. When an automated layout appears, notice that nobody chose where most of those cells went.

### Evidence limit

{{checklist: What this episode establishes | +the design flow is automated | +verification combines simulation and proof | -what any specific company does internally | ?how much effort each stage takes}}
This episode describes the general design flow as it is taught and as public standards define it. It does not establish what any specific company does internally. Detailed flows, tools and schedules are commercially confidential, and they vary between a small sensor chip and a large processor. Figures for how much effort each stage takes come largely from industry surveys and are not settled. Nor does verification guarantee correctness. Shipped chips have contained errors that every check missed, which is exactly why errata exist. The design flow reduces the risk of a wrong chip. It does not remove it.

### Closing

{{text}}
A modern chip is first a text, then a list, then a picture no person drew, and only at the very end a physical object. It is trustworthy not because anyone saw it work. It is trustworthy because each layer was checked against the one beneath it, and the bottom layer was measured.

## Editorial gate

*What this episode does that a template would not. Every line below is a property the pipeline enforces at build time — see V36 in `loop/validate.py`. It records no step a human still owes.*

- Humanized cold open: PRESENT
- First-person producer observation: FROM POV BANK (pov-038)
- Evidence uncertainty or limitation: COMPLETE
- Structural variation: follows the design flow top to bottom, from text to gates to geometry to silicon, and uses the producer's observation question to turn simulation into an evidence problem
- Number-level source audit: COMPLETE

## Chapters

- 00:00 Cold open
- 00:50 Title card
- 00:53 A chip begins as a description of behaviour, not a picture
- 02:55 Synthesis turns code into gates a factory already knows how to make
- 04:35 Placement and routing are optimisation problems handed to algorithms
- 06:30 Producer POV
- 06:40 Most of the work is proving the design is right
- 08:50 Physical rules are checked before any mask is made
- 10:30 The first silicon is still an experiment
- 11:50 What to notice in the edit
- 12:30 Evidence limit
- 13:10 Closing

## Sources

- IEEE: Institute of Electrical and Electronics Engineers home — https://www.ieee.org/
- IEEE: IEEE Standards Association (Verilog and VHDL standards) — https://standards.ieee.org/
- IEEE: IEEE Spectrum (semiconductor history, Intel 4004, Moore's observation) — https://spectrum.ieee.org/
- SEMI: SEMI home (industry association and standards, including OASIS) — https://www.semi.org/
- NIST: National Institute of Standards and Technology home (semiconductor measurement science) — https://www.nist.gov/
- MIT: Massachusetts Institute of Technology home — https://www.mit.edu/