/**
 * Two orthogonal axes carried by every question page.
 *
 * `subject` is how a reader browses. `method` is how the answer is known, and is
 * the axis that links pages across subjects: the same method recurs whether the
 * question is about a trench or a galaxy. Both are first-class fields on every
 * record so that adding a second subject never requires a content migration.
 *
 * The subject vocabulary mirrors the owner's admitted domains. A subject only
 * appears in navigation once at least one published page carries it — the
 * vocabulary is a constraint on the field, never a set of empty shelves.
 */

export type SubjectId =
  | 'deep-sea'
  | 'ocean-technology'
  | 'marine-geology'
  | 'expeditions'
  | 'earth-science'
  | 'space'
  | 'engineering-failures'
  | 'natural-history'
  | 'archaeology'
  | 'incident-analysis'

export type MethodId =
  | 'measured-by-instrument'
  | 'inferred-from-proxy'
  | 'observed-once'
  | 'dated-by-decay'
  | 'reconstructed-from-fragments'

export type SubjectDefinition = { id: SubjectId; name: string; blurb: string; accent: string }
export type MethodDefinition = { id: MethodId; name: string; blurb: string }

/** Accent is the only token permitted to vary by subject. Type, layout and the mark are fixed. */
export const subjects: SubjectDefinition[] = [
  { id: 'deep-sea', name: 'Deep sea', blurb: 'Ocean science below the last sunlight.', accent: 'var(--color-water-300)' },
  { id: 'ocean-technology', name: 'Ocean technology', blurb: 'Submersibles, ROVs, sonar and the instruments that reach depth.', accent: 'var(--color-glow)' },
  { id: 'marine-geology', name: 'Marine geology', blurb: 'Trenches, vents and the mapped shape of the seafloor.', accent: 'var(--color-accent)' },
  { id: 'expeditions', name: 'Expeditions', blurb: 'Exploration history and the record each expedition left.', accent: 'var(--color-water-500)' },
  { id: 'earth-science', name: 'Earth science', blurb: 'Weather, climate mechanics, geology and volcanology.', accent: 'var(--color-water-500)' },
  { id: 'space', name: 'Space', blurb: 'Astronomy and the measurement of distance and time at scale.', accent: 'var(--color-glow)' },
  { id: 'engineering-failures', name: 'Engineering failures', blurb: 'Forensic analysis of things that broke.', accent: 'var(--color-accent)' },
  { id: 'natural-history', name: 'Natural history', blurb: 'Animal adaptation and the fossil and field record.', accent: 'var(--color-water-300)' },
  { id: 'archaeology', name: 'Archaeology', blurb: 'Ancient technology and what survives of it.', accent: 'var(--color-accent)' },
  { id: 'incident-analysis', name: 'Incident analysis', blurb: 'Aviation and maritime incidents and their evidence trail.', accent: 'var(--color-water-500)' },
]

export const methods: MethodDefinition[] = [
  {
    id: 'measured-by-instrument',
    name: 'Measured by instrument',
    blurb:
      'A number produced by a device placed in the environment — a pressure sensor, a sonar beam, a calibrated camera. The instrument, and its stated error, is the evidence.',
  },
  {
    id: 'inferred-from-proxy',
    name: 'Inferred from a proxy',
    blurb:
      'The quantity itself was never touched. Something correlated with it was, and the answer is only as good as the link between the two.',
  },
  {
    id: 'observed-once',
    name: 'Observed once',
    blurb:
      'A single recorded encounter. The record is real but the sample is one, so it establishes that something happened rather than how often.',
  },
  {
    id: 'dated-by-decay',
    name: 'Dated by decay',
    blurb:
      'An age read from a process that runs at a known rate. The clock is physical; the uncertainty comes from calibration and contamination.',
  },
  {
    id: 'reconstructed-from-fragments',
    name: 'Reconstructed from fragments',
    blurb:
      'A whole assembled from incomplete remains or partial records. Reconstruction is inference, and the missing pieces set the limits.',
  },
]

const subjectById = new Map(subjects.map((item) => [item.id, item]))
const methodById = new Map(methods.map((item) => [item.id, item]))

export function getSubject(id: string) { return subjectById.get(id as SubjectId) }
export function getMethod(id: string) { return methodById.get(id as MethodId) }
export function isSubjectId(id: string): id is SubjectId { return subjectById.has(id as SubjectId) }
export function isMethodId(id: string): id is MethodId { return methodById.has(id as MethodId) }
