/**
 * The title and description every page ships, in one place.
 *
 * Why a table and not the page's own prose: a search result has a hard shape.
 * A title outside 30–65 characters is either padded with the site name or cut
 * mid-word, and a description outside 120–160 is either a fragment or truncated
 * by the engine. Measured on the live site on 2026-10-25, 15 of 54 pages had a
 * title outside that band (the homepage's was 11 characters, "How We Know") and
 * 50 of 54 had a description outside it. A page's visible summary is written for
 * a reader mid-page and is the wrong length for a result line by nature, so the
 * two are now separate strings with separate jobs.
 *
 * `title` is the bare title: pageMeta() appends " | How We Know" (14 characters),
 * so a bare title of 16–51 characters lands in the band with the site name
 * exactly once. scripts/validate-seo-meta.mjs measures the composed value for
 * every route in the prerender universe and fails on a gap, a length outside the
 * band, or a duplicate — and scripts/validate-built-html.mjs measures it again in
 * the emitted HTML, which is what a crawler actually reads.
 */
export type SeoCopy = { title?: string; description: string }

/**
 * Keyed by route path without a trailing slash; '/' is the homepage.
 *
 * `title` is omitted where the page's own title is already a good search result
 * in the band — every question page's title is the question itself, which is the
 * query a reader typed, and nothing improves on that.
 */
export const seoCopy: Record<string, SeoCopy> = {
  '/': {
    title: 'Deep-ocean answers and how we know them',
    description:
      'Evidence-backed answers about the deep ocean. Every page names the instrument, the proxy or the one observation behind it, and where the evidence stops.',
  },
  '/questions': {
    title: 'Every deep-sea question, answered first',
    description:
      'Direct answers to real questions about deep-sea animals, pressure, colour, light and ocean zones, each one sourced and answered in its first forty words.',
  },
  '/zones': {
    title: 'Ocean zones from sunlight to the trenches',
    description:
      'A reference guide to the sunlight, twilight, midnight, abyssal and hadal zones: the depth, light, temperature and pressure that define each layer.',
  },
  '/creatures': {
    title: 'Deep-sea creatures and their adaptations',
    description:
      'A starter library of iconic deep-sea animals, each with the depth it lives at, the adaptation behind its appearance and the evidence that records it.',
  },
  '/watch': {
    title: 'Watch the evidence behind each answer',
    description:
      'Every published How We Know video, paired with the sourced page it was built from, so the claim on screen and the claim in writing stay the same claim.',
  },
  '/explore': {
    title: 'Scroll the ocean from sunlight to hadal',
    description:
      'An interactive depth line placing zones, pressure, light, temperature and representative creatures on one continuous scroll from the surface to 10,935 m.',
  },
  '/methods': {
    title: 'How we know it: the evidence methods',
    description:
      'Answers grouped by how they are known: measured by instrument, inferred from a proxy, observed once, or reconstructed from fragments of the record.',
  },
  '/methods/measured-by-instrument': {
    title: 'Measured by instrument: what that means',
    description:
      'Answers that rest on a reading taken by a sonar, a pressure sensor, a camera or a probe, and on how precisely that instrument can be trusted at depth.',
  },
  '/methods/inferred-from-proxy': {
    title: 'Inferred from a proxy: what that means',
    description:
      'Answers that rest on a stand-in rather than the thing itself, and on how much the stand-in can carry before the inference stops being safe to make.',
  },
  '/methods/observed-once': {
    title: 'Observed once: what a single sighting means',
    description:
      'Answers that rest on one recorded observation, why a single sighting is still evidence, and why it cannot carry a claim about how common something is.',
  },
  '/methods/reconstructed-from-fragments': {
    title: 'Reconstructed from fragments: what it means',
    description:
      'Answers assembled from incomplete remains and partial records, and the gap between what the fragments show and what the living animal actually did.',
  },
  '/methodology': {
    title: 'How questions, sources and claims are set',
    description:
      'How How We Know admits a question, selects sources, handles uncertainty, and keeps the claim in an article and the claim in its video identical.',
  },
  '/editorial-policy': {
    title: 'Editorial policy: review and corrections',
    description:
      'The review, correction and citation rules this site runs on: who checks a claim, what happens when one turns out wrong, and how a source is credited.',
  },
  '/about': {
    title: 'About How We Know and who publishes it',
    description:
      'How We Know is an evidence-first publication about the deep ocean, written and reviewed to one rule: name the evidence, and say where the evidence stops.',
  },
  '/privacy': {
    title: 'Privacy: what this site does with data',
    description:
      'What How We Know collects, what it does not, which third parties are involved in video playback and analytics, and how to ask for data to be deleted.',
  },
  '/terms': {
    title: 'Terms of Service for using this site',
    description:
      'The terms for reading, quoting and citing How We Know, the limits of the answers published here, and the rules that apply to the videos they pair with.',
  },
  '/questions/why-deep-sea-creatures-look-so-weird': {
    description:
      'Large teeth, transparent heads and glowing lures are answers to darkness, pressure, cold and scarce food. Here is the evidence behind each of those shapes.',
  },
  '/questions/how-deep-sea-creatures-survive-pressure': {
    description:
      'Deep-sea animals are mostly water and carry no large gas spaces, so pressure does not crush them. Why that works, and why a fast ascent still harms them.',
  },
  '/questions/why-deep-sea-creatures-are-surfacing': {
    description:
      'Midwater animals rise to feed every night and sink before dawn. How to tell that ordinary migration from a genuinely unusual deep-sea animal at the surface.',
  },
  '/questions/why-deep-sea-creatures-are-so-scary': {
    description:
      'Large teeth, black eyes and unfamiliar proportions read as threat to us. In the deep sea they are feeding and camouflage adaptations, not aggression at all.',
  },
  '/questions/why-many-deep-sea-creatures-are-red': {
    description:
      'Red light is absorbed near the surface, so it never reaches deep water. A red animal reflects almost nothing down there and is effectively invisible.',
  },
  '/questions/why-some-deep-sea-creatures-are-transparent': {
    description:
      'Transparency erases the outline and shadow of an animal in open water where there is nothing to hide behind, and some organs still stay stubbornly visible.',
  },
  '/questions/why-deep-sea-creatures-get-creepier-deeper': {
    title: 'Do deep-sea animals get creepier with depth?',
    description:
      'They do not objectively get creepier. As sunlight and food disappear and pressure rises, the adaptations that pay off change, and so do the bodies you see.',
  },
  '/questions/what-creatures-live-in-the-deep-sea': {
    description:
      'Fishes, squid, octopuses, jellies, crustaceans, worms, corals and sponges, set out zone by zone with the depth each group occupies below the sunlit ocean.',
  },
  '/questions/what-is-the-scariest-deep-sea-creature': {
    description:
      'There is no scientific answer, and this explains why: a reality-based comparison of the anglerfish, viperfish, giant squid and isopod people name most.',
  },
  '/questions/what-is-the-deepest-part-of-the-ocean': {
    description:
      'Challenger Deep in the Mariana Trench, about 10,935 metres down. Where it is, why published figures differ by metres, and what conditions exist at the floor.',
  },
  '/questions/what-is-a-dumbo-octopus': {
    description:
      'A finned deep-sea octopus of the cirrate group that swims with ear-like fins and webbed arms, from the deep seafloor down into the hadal zone.',
  },
  '/questions/what-is-a-frilled-shark': {
    description:
      'A rare eel-bodied shark with six pairs of frilled gill slits and flexible jaws, and why the popular living-fossil story about it goes further than evidence.',
  },
  '/questions/how-does-bioluminescence-work-in-the-deep-sea': {
    description:
      'Light made by chemical reactions inside an animal, used for camouflage, for luring prey and for signalling. How the reaction works and who uses which job.',
  },
  '/questions/how-big-is-a-colossal-squid': {
    description:
      'The heaviest known invertebrate: Te Papa\'s preserved female weighs 495 kilograms. Measured size, record eyes, rotating hooks, and what specimens cannot show.',
  },
  '/questions/how-do-people-reach-challenger-deep': {
    description:
      'Crewed submersibles built to survive nearly eleven kilometres of water. The engineering, navigation, history and measurement behind each dive to the floor.',
  },
  '/questions/what-happens-when-a-whale-dies-in-the-deep-ocean': {
    description:
      'A whale fall: one carcass becomes an island of food for scavengers, worms, microbes and chemosynthetic communities, in stages that can run for decades.',
  },
  '/questions/what-is-a-yeti-crab': {
    description:
      'Deep-sea crustaceans of the family Kiwaidae that grow chemosynthetic bacteria on hair-like setae, and some species then harvest that growth as their food.',
  },
  '/questions/why-does-black-smoker-water-not-boil': {
    description:
      'Seafloor pressure raises water\'s boiling point, so hydrothermal fluid can pass 340C and stay liquid, then precipitate minerals into a black plume.',
  },
  '/questions/what-is-the-deepest-fish-ever-recorded': {
    description:
      'A snailfish filmed at 8,336 metres in the Izu-Ogasawara Trench. Why juveniles may go deepest, and the physiological limit that keeps fish off the deepest floor.',
  },
  '/questions/what-is-the-midnight-zone': {
    description:
      'The bathypelagic zone, roughly 1,000 to 4,000 metres: no sunlight at all, scarce food, and animals that live on living light and low-energy strategies.',
  },
  '/creatures/anglerfish': {
    title: 'Deep-sea anglerfish and its glowing lure',
    description:
      'A diverse group of deep-sea fishes best known for a lit lure that brings prey within striking distance in water with no sunlight left in it at all.',
  },
  '/creatures/vampire-squid': {
    title: 'Vampire squid: the marine-snow eater',
    description:
      'Despite the name, a slow low-energy cephalopod that collects marine snow drifting down from above rather than hunting prey the way a typical squid does.',
  },
  '/creatures/barreleye': {
    title: 'Barreleye fish and its transparent head',
    description:
      'A fish whose tubular eyes sit inside a clear fluid-filled shield, letting it look straight upward through its own head to track prey against faint light.',
  },
  '/creatures/giant-squid': {
    title: 'Giant squid: what has been observed',
    description:
      'A rarely observed open-ocean squid with exceptionally large eyes and long feeding tentacles, known mostly from strandings and a handful of filmed encounters.',
  },
  '/creatures/dumbo-octopus': {
    title: 'Dumbo octopus and its ear-like fins',
    description:
      'A deep-sea octopus that swims with fins shaped like ears and webbed arms, and which lacks the ink defence that shallower octopuses rely on to escape.',
  },
  '/creatures/hadal-snailfish': {
    title: 'Hadal snailfish: the deepest fish filmed',
    description:
      'Soft-bodied fishes of the hadal trenches, including the deepest fish yet confirmed on video, and the pressure limit that appears to stop them going deeper.',
  },
  '/creatures/dragonfish': {
    title: 'Deep-sea dragonfish and its light organs',
    description:
      'A small predatory fish with long teeth, highly sensitive eyes and light-producing organs, including species that emit red light almost nothing else can see.',
  },
  '/creatures/giant-isopod': {
    title: 'Giant isopod: the deep-sea scavenger',
    description:
      'A large crustacean scavenger that feeds on animal falls and whatever else sinks to the seafloor, and can go remarkably long between meals when nothing does.',
  },
  '/creatures/frilled-shark': {
    title: 'Frilled shark: biology, not living fossil',
    description:
      'A rare eel-shaped shark with six pairs of gill slits, three-pronged teeth and flexible jaws, and the evidence behind each part of its popular reputation.',
  },
  '/creatures/colossal-squid': {
    title: 'Colossal squid: the heaviest invertebrate',
    description:
      'The heaviest known invertebrate, with enormous eyes and rotating hooks on its tentacle clubs, measured from preserved specimens rather than living animals.',
  },
  '/creatures/yeti-crab': {
    title: 'Yeti crab and the farm on its own arms',
    description:
      'Deep-sea crustaceans that carry chemosynthetic bacteria on dense hair-like setae, with some species farming and then harvesting that growth as their food.',
  },
  '/zones/sunlight': {
    title: 'Sunlight Zone: where photosynthesis works',
    description:
      'The upper ocean, roughly 0 to 200 metres, where enough light reaches for photosynthesis and where most familiar marine food webs actually begin.',
  },
  '/zones/twilight': {
    title: 'Twilight Zone: the nightly migration layer',
    description:
      'A dim global layer from about 200 to 1,000 metres, where enormous numbers of animals rise toward the surface each night and descend again before dawn.',
  },
  '/zones/midnight': {
    title: 'Midnight Zone: the largest dark habitat',
    description:
      'The largest continuously dark habitat on Earth, roughly 1,000 to 4,000 metres, where food is scarce and animals live on lures, senses and low-energy budgets.',
  },
  '/zones/abyss': {
    title: 'Abyssal Zone above the deep seafloor',
    description:
      'A vast, cold region from about 4,000 to 6,000 metres, supplied almost entirely by organic material sinking down from the lit water far above it.',
  },
  '/zones/hadal': {
    title: 'Hadal Zone: the ocean\'s deepest trenches',
    description:
      'The trench zone below about 6,000 metres: narrow, extremely deep habitats with their own communities and the highest pressures anywhere in the ocean.',
  },
}
