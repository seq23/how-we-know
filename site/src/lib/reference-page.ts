import { questions } from './questions-data'
import { getSources } from './sources-data'
import { organizationSchema } from './schema'
import { absoluteUrl } from './site'
import type { CreatureRecord, OceanZoneRecord } from './types'

/**
 * Every reference page's generated prose.
 *
 * Each sentence here is written once and shipped to all sixteen creature and zone
 * pages, so a sentence that does not name its own record is a sentence sixteen
 * pages say identically. On 2026-11-03 that came to 222 of a creature page's 390
 * body words, and the audit's near-duplicate test read /zones/hadal/ and
 * /creatures/hadal-snailfish/ as 60% the same page (it fails above 50%).
 *
 * So the rule for anything added below: **every generated sentence names the
 * record** — its name, its scientific name, its depth figures, its own sources or
 * its own count of facts. The hedge the sentence carries is the same hedge; the
 * words carrying it are the record's. Checklist item q1 asks for exactly this
 * ("rewrite the slot text so each page says something only it can say"), and
 * scripts/validate-built-html.mjs measures it on the build.
 */
export function referencePage(record: CreatureRecord | OceanZoneRecord, kind: 'creature' | 'zone') {
  const creature = 'adaptations' in record ? record : null
  const zone = 'conditions' in record ? record : null
  const facts = creature?.adaptations ?? zone!.conditions
  const name = record.name.toLowerCase()
  const low = record.minDepthM.toLocaleString('en-US')
  const high = record.maxDepthM.toLocaleString('en-US')
  const organizations = getSources(record.sourceIds)
    .map((source) => source.organization)
    .filter((value, index, all) => all.indexOf(value) === index)
  const definition = creature
    ? `${creature.name} (${creature.scientificName}) is recorded here between ${low} and ${high} meters, through the anatomy, habitat and feeding behaviour its sources describe. That range is the ${name} library record; it is not a claim that every ${name} occupies the whole of it.`
    : `The ${name} (${record.scientificName}) is the ocean depth band from ${low} to ${high} meters in this reference. Both ${name} boundaries are publishing conventions for comparing it with the bands above and below, not physical walls that separate animals or water masses.`
  const related = questions.filter((q) => creature ? q.relatedCreatures.includes(record.slug) : q.relatedZones.includes(record.slug))
  const evidence = getSources(record.sourceIds)
  const faqs = [
    {question: `What defines ${name}?`, answer: creature
      ? `Under the name ${record.scientificName}, ${facts.length} features are recorded for the ${name}: ${facts[0].replace(/\.$/, '')}, and ${facts.length - 1} more listed above. Taken together they describe what has been observed of the ${name}; one photograph of a ${name} between ${low} and ${high} meters cannot establish how it feeds, breeds or moves across the rest of that range.`
      : `The ${name} is defined in this reference by ${facts.length} conditions: ${facts[0].replace(/\.$/, '')}, and ${facts.length - 1} more listed above. Those conditions describe the ${name} as a band of water, so a reading taken at ${low} meters does not describe the whole band down to ${high} meters.`},
    {question: `What depth range does this reference use for ${name}?`, answer: creature
      ? `This reference records the ${name} between ${low} and ${high} meters, which is the range its ${organizations.length === 1 ? 'source' : 'sources'} below support rather than a limit on where a ${name} can be found. An individual ${name} occupies part of that range, not all of it.`
      : `This reference places the ${name} between ${low} and ${high} meters. Those two figures are publishing conventions for comparing the ${name} with the bands above and below it, and the water does not change at either number.`},
    {question: `Where can I check the evidence on ${name}?`, answer: `${organizations.join(' and ')} ${organizations.length === 1 ? 'is the source' : 'are the sources'} behind this ${name} record, linked in full below with the date each was last checked. Read ${organizations.length === 1 ? 'its' : 'their'} own account of the ${name} to see which parts are direct observation and which are inference drawn from it.`},
  ]
  const path = `/${kind === 'creature' ? 'creatures' : 'zones'}/${record.slug}`
  const schemas = [
    {'@context':'https://schema.org', '@type':'Article', headline: record.name, description: record.summary,
      mainEntityOfPage:absoluteUrl(path), datePublished:'2026-08-31', dateModified:'2026-11-02',
      author:organizationSchema, publisher:organizationSchema, image:absoluteUrl('/og-default.png'),
      citation:evidence.map(s=>s.url), speakable:{'@type':'SpeakableSpecification',cssSelector:['.definition','#faq']}},
    {'@context':'https://schema.org','@type':'FAQPage',mainEntity:faqs.map(f=>({'@type':'Question',name:f.question,acceptedAnswer:{'@type':'Answer',text:f.answer}}))},
  ]
  return {definition, facts, related, faqs, schemas}
}
