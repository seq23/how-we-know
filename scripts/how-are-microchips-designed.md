# How are microchips designed?

**Status:** DRAFT — OWNER CONFIRMATION AND MASTER WATCH REQUIRED
**Domain:** materials-and-manufacturing
**Reopened:** 2026-10-13 (loop/lengthen.py reopen, hook rule)
**Opening:** stake-then-payoff
**Word count:** ~1740
**Estimated narration:** 12m 2s at 144.58 WPM (measured, loop/durations.py)

## YouTube title

Microchips are designed as written text, not drawn by hand — and how we know

## Direct-answer lock

Microchips are designed mostly as text: engineers describe a chip's behaviour in a hardware description language such as Verilog or VHDL, and software tools translate that description into logic gates and then into the geometric layout of billions of transistors. Most of the effort goes not into drawing the chip but into proving the design correct before anything is manufactured, through simulation, formal proofs and checks against the factory's own rules.

## Narration

### Cold open

Chipmakers publish lists of bugs in chips they have already shipped. Those lists exist because of how the work is done. Microchips are designed mostly as text: engineers describe a chip's behaviour in a hardware description language such as Verilog or VHDL, and software tools translate that description into logic gates and then into the geometric layout of billions of transistors. Both languages are IEEE standards. Most effort goes into proving the design before manufacture, through simulation, formal proofs and the foundry's rules. Those checks reduce risk, and the errata show they cannot remove it.

### Title card

How are microchips designed?

### A chip begins as a description of what it does

{{define: Hardware description language | text that describes structure and behaviour that exist all at once | it does not describe steps to be run one after another | IEEE}}
Start with the language, because that is where the design actually lives. A hardware description language looks like code, and engineers type it in an editor like any programmer. But it does not describe steps to be run one after another. It describes structure and behaviour that exist all at once: these signals connect here, this value updates on every tick of the clock, this block waits for that one. The two dominant languages, Verilog and VHDL, along with an extended form called SystemVerilog, are published as standards by the IEEE. That is how every tool vendor and every design team can agree on what a given line of text means. The agreement is not a detail. Without a shared, written definition of the language, a design could mean one thing in the simulator and something slightly different in the tool that builds it.

{{text}}
Most designs are written at what engineers call the register-transfer level. A register is a small store that holds a value. The description says how values move between registers, and what logic transforms them on the way, at each edge of the clock. Nothing at this level says where a transistor sits or how long a wire is. That separation is deliberate. It lets a team reason about what the chip should compute before anyone decides what it physically looks like, and it lets the same description be rebuilt for a different factory later.

### Synthesis turns the description into gates the factory already knows how to make

{{chain: Logic synthesis | register-transfer description | standard cells | >netlist}}
The next step is called logic synthesis, and it is done by software. The synthesis tool reads the register-transfer description and maps it onto a library of standard cells. A standard cell is a small, pre-designed circuit — a gate that performs AND, a gate that inverts a signal, a storage element called a flip-flop — drawn and characterised in advance for one specific manufacturing process. The factory, usually called a foundry, or a library vendor working with it, has measured how fast each cell switches and how much power it draws under different conditions of voltage and temperature. The output of synthesis is a netlist: a list of cells and the wires that connect them.

{{contrast: Equivalence checking | is=a proof for every input | not=a test that tries examples}}
Here is the first place the "how we know" question bites. Synthesis does not simply translate; it optimises, rewriting logic to be smaller or faster. So the netlist is not a line-by-line copy of what the engineer wrote. To confirm the two still mean the same thing, teams run equivalence checking, a formal method that proves mathematically that the netlist and the original description produce identical outputs for every input. It is not a test that tries examples. It is a proof for every input, and that difference matters for everything that follows.

### Producer POV

[HUMAN] Deep-sea science builds conclusions from incomplete observations, damaged specimens, sonar, water samples and tiny windows of footage.

### Verification samples behaviour, then proves what it can

{{checklist: Verification evidence | +testbench | +reference model | +coverage | ?states never visited}}
That question, asked about animals, is exactly the right one to ask about chips. A modern processor has far more possible internal states than any simulation could ever visit. So no one observes a chip's behaviour exhaustively. Verification engineers build a testbench, a surrounding program that feeds the design inputs and checks its outputs against a reference model of what should happen. On many teams verification takes more effort than writing the design itself, though published estimates of the split vary and this script will not quote one. Engineers generate constrained random stimulus, enormous numbers of plausible but unplanned input sequences, because bugs hide in combinations no one thought to write by hand. Then they measure coverage: which lines executed, which states were reached, which scenarios the plan said must occur.

{{steps: Verification | simulation | coverage | formal verification | emulation | >each method covers a gap the others leave}}
Coverage is the honest part. It tells the team what was exercised and, by subtraction, what was not. Where simulation cannot reach, formal verification steps in. A tool is given a property — this buffer never overflows, these two requests are never granted at once — and searches for any sequence of inputs that breaks it. If none exists, the property is proven within the bounds the tool was given. For large designs, teams also load the description onto emulation hardware, or onto reconfigurable chips called FPGAs, which run the logic far faster than simulation and let real software boot on a design that does not physically exist yet. Each method covers a gap the others leave.

### Physical design turns a list of gates into geometry

{{chain: Physical design | floorplanning | placement | clock tree synthesis | routing | >metal wires that connect everything}}
Only now does the chip acquire a shape. Physical design begins with floorplanning: deciding where large blocks such as memories and processor cores will sit, and how power reaches them. Placement software then positions every standard cell from the netlist. Clock tree synthesis builds the network that delivers the clock signal so that it arrives at every flip-flop at nearly the same moment. Routing draws the metal wires that connect everything, stacked in many layers above the transistors. All of this is automated, because the number of cells is far too large for hands, but engineers steer it constantly, adjusting constraints and re-running when results fall short.

{{define: Static timing analysis | adds up the delay along every path between registers | only as good as the delay models it is fed | foundry}}
How do they know when results fall short? Mainly through static timing analysis. Instead of simulating signals, the tool adds up the delay along every path between registers, using the characterised cell data and estimates of wire delay, and checks that each signal arrives before the next clock edge. A path that is too slow is called a timing violation. Static timing analysis is powerful because it is exhaustive over paths without needing any input patterns. Its boundary is that it is only as good as the delay models it is fed, which is why the careful measurement work done by the foundry matters so much.

### Signoff checks the layout against the factory's own rules

{{checklist: Signoff | +design rule checking | +layout versus schematic | +parasitic extraction | +timing is checked again}}
Before a design leaves the team, it goes through signoff. Design rule checking compares every shape in the layout against the foundry's rule set: minimum widths, minimum spacings, how layers may overlap. Those rules encode what the manufacturing process can reliably print. Layout versus schematic checking extracts the circuit that the geometry actually forms and confirms it matches the netlist. Parasitic extraction calculates the resistance and capacitance of the real wires, and timing is checked again with those values. A design that passes all of this is handed off in a step still called tape-out, a name commonly traced to the era when layouts were shipped on magnetic tape.

{{sources: Shared standards | IEEE=hardware description languages | SEMI=SEMI International Standards | NIST=semiconductor metrology}}
The layout becomes a set of photomasks, the stencils used to pattern each layer of the wafer. Here the design world meets the public standards bodies. SEMI, the industry association for semiconductor manufacturing, publishes the SEMI International Standards used across equipment, materials and masks, so that a design from one company can be built with tools from many others. NIST, the United States national measurement institute, works on semiconductor metrology — how to measure features far too small to see, and how sure anyone can be of that measurement. These bodies do not design chips. They supply the shared definitions and measurements that let a design be trusted outside the room it was made in.

### The first chips back from the factory are the real experiment

{{steps: First silicon | bring-up | scan chains | automated test equipment | >design for test}}
Everything up to tape-out is prediction. The first wafers back from the foundry are where prediction meets matter. Engineers run bring-up: they power the first chips, check that clocks start, load test software, and compare behaviour against the models. To make this possible, designers add circuitry whose only purpose is to be tested. Scan chains link the flip-flops so their contents can be shifted out and read, which lets automated test equipment check each manufactured chip for physical defects. This practice is called design for test, and it is why a chip can be checked after manufacture, not only before.

{{contrast: Verification | is=reduces risk | not=removing it}}
When bring-up finds a bug that slipped through, the outcome depends on where it lives. Some bugs can be worked around in software or firmware. Others require a respin: corrected masks and another trip through the factory, which costs time and money. Manufacturers also publish lists of known bugs in shipped products, usually called errata. Those documents are some of the most candid public evidence about chip design, because they show directly that verification reduces risk without removing it.

### What to notice in the edit

{{text}}
In the edit, watch for the shift between two kinds of evidence. Some steps, like equivalence checking, formal proofs and static timing analysis, are exhaustive within a stated model. Others, like simulation and bring-up, are samples. The animation draws those differently. A proven claim is drawn solid; a sampled one is drawn as scattered points with gaps between them. Whenever you see the gaps, that is the honest picture of what testing alone can show.

### Evidence limit

{{checklist: What this establishes | +the method | -how any particular company runs its flow | -that any shipped chip is free of bugs}}
This account describes the method as public standards and teaching material lay it out. It does not establish how any particular company runs its flow. Those details, including the tools chosen, the size of teams and the cost of a design, are mostly proprietary, and published estimates vary so widely that this script states none of them. It also does not establish that any shipped chip is free of bugs. Verification proves properties inside models, and the models themselves are assumptions about how silicon behaves. The published errata are the reminder of where that gap shows.

### Closing

{{ambient}}
So a microchip is designed the way a careful argument is written: stated in a precise language, translated step by step, and checked at each step against something it must agree with. The chip you are holding is the last link in that chain. The evidence that it works is not one test, but the agreement of all of them.

## Editorial gate

*What this episode does that a template would not. Every line below is a property the pipeline enforces at build time — see V36 in `loop/validate.py`. It records no step a human still owes.*

- Humanized cold open: PRESENT
- First-person producer observation: FROM POV BANK (pov-038)
- Evidence uncertainty or limitation: COMPLETE
- Structural variation: a digit-free design-flow walk-through that sorts every step into proof versus sample, ending on first silicon as the real experiment
- Number-level source audit: COMPLETE

## Chapters

- 00:00 Cold open
- 00:50 Title card
- 00:53 A chip begins as a description of what it does
- 02:22 Synthesis turns the description into gates the factory already knows how to make
- 03:42 Producer POV
- 03:50 Verification samples behaviour, then proves what it can
- 05:38 Physical design turns a list of gates into geometry
- 07:10 Signoff checks the layout against the factory's own rules
- 08:46 The first chips back from the factory are the real experiment
- 10:00 What to notice in the edit
- 10:32 Evidence limit
- 11:15 Closing

## Sources

- IEEE: Institute of Electrical and Electronics Engineers home — https://www.ieee.org/
- IEEE Standards Association: standards including hardware description languages — https://standards.ieee.org/
- SEMI: SEMI and SEMI International Standards — https://www.semi.org/
- NIST: National Institute of Standards and Technology, semiconductor measurement work — https://www.nist.gov/