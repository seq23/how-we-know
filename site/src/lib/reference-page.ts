import { questions } from './questions-data'
import { getSources } from './sources-data'
import { organizationSchema } from './schema'
import { absoluteUrl } from './site'
import type { CreatureRecord, OceanZoneRecord } from './types'

export function referencePage(record: CreatureRecord | OceanZoneRecord, kind: 'creature' | 'zone') {
  const creature = 'adaptations' in record ? record : null
  const zone = 'conditions' in record ? record : null
  const facts = creature?.adaptations ?? zone!.conditions
  const definition = creature
    ? `${creature.name} (${creature.scientificName}) is described here through its recorded anatomy, habitat and feeding adaptations. ${creature.summary} The reference depth range is ${creature.minDepthM.toLocaleString('en-US')}–${creature.maxDepthM.toLocaleString('en-US')} meters; this describes the library record, rather than a claim that every individual occupies the whole range.`
    : `The ${record.name.toLowerCase()} (${record.scientificName}) is the ocean depth band from ${record.minDepthM.toLocaleString('en-US')} to ${record.maxDepthM.toLocaleString('en-US')} meters in this reference. ${record.summary} These boundaries are publishing conventions for comparing habitats, rather than physical walls separating animals or water masses.`
  const related = questions.filter((q) => creature ? q.relatedCreatures.includes(record.slug) : q.relatedZones.includes(record.slug))
  const evidence = getSources(record.sourceIds)
  const faqs = [
    {question: `What defines ${record.name.toLowerCase()}?`, answer: `${record.summary} ${facts.join('. ')}. These features describe the reference record together; a single photograph or observation cannot establish every aspect of an animal's life or the whole range of conditions within an ocean habitat.`},
    {question: `What depth range does this reference use?`, answer: `This reference uses ${record.minDepthM.toLocaleString('en-US')}–${record.maxDepthM.toLocaleString('en-US')} meters for ${record.name.toLowerCase()}. Depth provides context for interpreting the record alongside its sources. It is not a claim that conditions are identical throughout the range, or that an observation at one depth describes every animal associated with it.`},
    {question: `Where can I check the evidence?`, answer: `Start with ${evidence.map(s=>s.organization).filter((v,i,a)=>a.indexOf(v)===i).join(' and ')}, linked in the source list below. Follow the original account to distinguish direct observation from inference. Related answers explain the mechanisms in more detail; their source lists identify the evidence behind individual figures and interpretations.`},
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
