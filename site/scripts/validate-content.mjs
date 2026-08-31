import { assert, assertUnique, isHttpsUrl, isIsoDate, readJson, wordCount } from './validation-helpers.mjs'

const questions = readJson('content/questions.json')
const sources = readJson('content/sources.json')
const zones = readJson('content/zones.json')
const creatures = readJson('content/creatures.json')

const sourceIds = new Set(sources.map((item) => item.id))
const zoneIds = new Set(zones.map((item) => item.slug))
const creatureIds = new Set(creatures.map((item) => item.slug))

assertUnique(questions.map((item) => item.slug), 'question slug')
assertUnique(zones.map((item) => item.slug), 'zone slug')
assertUnique(creatures.map((item) => item.slug), 'creature slug')
assertUnique(sources.map((item) => item.id), 'source id')
assertUnique(sources.map((item) => item.url), 'source URL')
assert(questions.length === 20, `Expected 20 admitted questions, found ${questions.length}`)
assert(zones.length === 5, `Expected 5 ocean zones, found ${zones.length}`)

for (const source of sources) {
  assert(source.id && source.name && source.organization, `Incomplete source record: ${source.id || 'unknown'}`)
  assert(isHttpsUrl(source.url), `Source ${source.id} must use an absolute HTTPS URL`)
  assert(isIsoDate(source.checkedAt), `Source ${source.id} has invalid checkedAt date`)
  assert(source.notes.trim().length >= 20, `Source ${source.id} needs a substantive provenance note`)
}

for (const question of questions) {
  assert(wordCount(question.directAnswer) >= 20, `${question.slug} direct answer is too thin`)
  assert(wordCount(question.directAnswer) <= 40, `${question.slug} direct answer exceeds 40 words`)
  assert(isIsoDate(question.publishedAt), `${question.slug} has invalid publishedAt date`)
  assert(isIsoDate(question.reviewedAt), `${question.slug} has invalid reviewedAt date`)
  assert(question.reviewedAt >= question.publishedAt, `${question.slug} reviewedAt predates publishedAt`)
  assert(question.sections.length >= 4, `${question.slug} needs at least 4 sections`)
  assert(question.faqs.length >= 4, `${question.slug} needs at least 4 FAQs`)
  assert(question.comparison.columns.length >= 3, `${question.slug} comparison needs at least 3 columns`)
  assert(question.comparison.rows.length >= 4, `${question.slug} comparison is too thin`)
  assert(question.sourceIds.length >= 3, `${question.slug} needs at least 3 source records`)
  assert(question.relatedZones.length >= 1, `${question.slug} needs at least one related zone`)
  assert(question.relatedCreatures.length >= 1, `${question.slug} needs at least one related creature`)
  assertUnique(question.faqs.map((faq) => faq.question), `${question.slug} FAQ`)

  const sectionWords = question.sections.reduce(
    (total, section) => total + section.paragraphs.reduce((sum, paragraph) => sum + wordCount(paragraph), 0),
    0,
  )
  assert(sectionWords >= 125, `${question.slug} explanatory body is too thin (${sectionWords} words)`)

  for (const section of question.sections) {
    assert(section.heading.trim().length >= 8, `${question.slug} has a weak section heading`)
    assert(section.paragraphs.length >= 1, `${question.slug}/${section.heading} has no paragraphs`)
  }

  for (const row of question.comparison.rows) {
    assert(
      row.length === question.comparison.columns.length,
      `${question.slug} comparison row does not match its column count`,
    )
  }

  assert(
    question.sourceIds.includes(question.keyStat.sourceId),
    `${question.slug} key-stat source must also appear in sourceIds`,
  )
  for (const id of question.sourceIds) {
    assert(sourceIds.has(id), `${question.slug} references missing source ${id}`)
  }
  for (const slug of question.relatedZones) {
    assert(zoneIds.has(slug), `${question.slug} references missing zone ${slug}`)
  }
  for (const slug of question.relatedCreatures) {
    assert(creatureIds.has(slug), `${question.slug} references missing creature ${slug}`)
  }
}

const orderedZones = [...zones].sort((left, right) => left.minDepthM - right.minDepthM)
assert(orderedZones[0].minDepthM === 0, 'Zone coverage must begin at the surface')
for (let index = 0; index < orderedZones.length; index += 1) {
  const zone = orderedZones[index]
  assert(zone.minDepthM < zone.maxDepthM, `${zone.slug} has an invalid depth range`)
  assert(zone.conditions.length >= 3, `${zone.slug} needs at least 3 defining conditions`)
  assert(zone.sourceIds.length >= 1, `${zone.slug} needs at least one source`)
  if (index > 0) {
    assert(
      orderedZones[index - 1].maxDepthM === zone.minDepthM,
      `Zone gap or overlap between ${orderedZones[index - 1].slug} and ${zone.slug}`,
    )
  }
  for (const id of zone.sourceIds) {
    assert(sourceIds.has(id), `${zone.slug} references missing source ${id}`)
  }
}
assert(orderedZones.at(-1).maxDepthM === 11000, 'Zone coverage must reach 11,000 meters')

for (const creature of creatures) {
  assert(creature.minDepthM < creature.maxDepthM, `${creature.slug} has an invalid depth range`)
  assert(creature.adaptations.length >= 3, `${creature.slug} needs at least 3 adaptations`)
  assert(creature.sourceIds.length >= 1, `${creature.slug} needs at least one source`)
  for (const id of creature.sourceIds) {
    assert(sourceIds.has(id), `${creature.slug} references missing source ${id}`)
  }
  for (const zone of creature.zones) {
    assert(zoneIds.has(zone), `${creature.slug} references unknown zone ${zone}`)
  }
}

const usedSources = new Set([
  ...questions.flatMap((item) => item.sourceIds),
  ...zones.flatMap((item) => item.sourceIds),
  ...creatures.flatMap((item) => item.sourceIds),
])
for (const source of sources) {
  assert(usedSources.has(source.id), `Source registry contains unused source ${source.id}`)
}

console.log('Content and provenance validation passed.')
