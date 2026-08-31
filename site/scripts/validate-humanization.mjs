import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'

const root = process.cwd()
const finalDir = path.join(root, 'production/scripts/final')
const plainDir = path.join(root, 'production/scripts/plaintext')
const passDir = path.join(root, 'production/human-pass')
const auditPath = path.join(root, 'production/research/number-verification.json')
const ledgerPath = path.join(root, 'production/human-pass/approval-ledger.json')
const exhaustiveAuditPath = path.join(root, 'production/research/number-verification-exhaustive.json')

const files = fs.readdirSync(finalDir).filter((name) => /^\d{2}-.*\.md$/.test(name)).sort()
const failures = []
if (files.length !== 20) failures.push(`Expected 20 final scripts; found ${files.length}`)

const banned = [
  'Narration quality gate',
  'A reusable source rule',
  'Context before spectacle',
  'Observation versus inference',
  'Before we finish, notice the pattern',
  'This matters because an adaptation is never just a visual effect',
  'welcome back',
  "don't forget to",
  'in this video',
  "let's dive in",
  'mind-blowing',
  "you won't believe",
  'little did they know',
  "the ocean's deepest secret",
]

const paragraphOwners = new Map()
const coldOpens = new Set()
const variations = new Set()
const results = []

function wordCount(text) {
  return (text.match(/\b[\p{L}\p{N}’'-]+\b/gu) || []).length
}

for (const name of files) {
  const mdPath = path.join(finalDir, name)
  const plainPath = path.join(plainDir, name.replace(/\.md$/, '.txt'))
  const passPath = path.join(passDir, name)
  const md = fs.readFileSync(mdPath, 'utf8')
  if (!fs.existsSync(plainPath)) {
    failures.push(`${name}: missing plaintext narration`)
    continue
  }
  if (!fs.existsSync(passPath)) {
    failures.push(`${name}: missing human-pass record`)
    continue
  }
  const plain = fs.readFileSync(plainPath, 'utf8').trim()
  const humanPass = fs.readFileSync(passPath, 'utf8')
  const narrationMatch = md.match(/## Narration\n([\s\S]*?)(?=\n## Human fingerprint gate)/)
  if (!narrationMatch) {
    failures.push(`${name}: missing narration block`)
    continue
  }
  const sections = narrationMatch[1]
    .split(/^### /m)
    .slice(1)
    .map((part) => {
      const newline = part.indexOf('\n')
      return { name: part.slice(0, newline).trim(), body: part.slice(newline + 1).trim() }
    })
  const cleanNarration = sections.map((section) => section.body).join('\n\n').trim()
  const count = wordCount(plain)
  if (count < 1150 || count > 1350) failures.push(`${name}: ${count} words; required 1150–1350`)
  if (md.split('[HUMAN]').length - 1 !== 1) failures.push(`${name}: Markdown must contain exactly one [HUMAN] marker`)
  if (plain.split('[HUMAN]').length - 1 !== 1) failures.push(`${name}: plaintext must contain exactly one [HUMAN] marker`)
  if (humanPass.split('[HUMAN]').length - 1 < 1) failures.push(`${name}: human-pass record must quote the drafted [HUMAN] observation`)
  if (!md.includes('### Evidence limit')) failures.push(`${name}: missing Evidence limit section`)
  if (!md.includes('Final human watch-through: PENDING')) failures.push(`${name}: final watch-through must remain visibly pending`)
  if (!humanPass.includes('Watch the final rendered MP4 from beginning to end')) failures.push(`${name}: missing full-master watch requirement`)
  if (!humanPass.includes('OWNER CONFIRMATION AND MASTER WATCH PENDING')) failures.push(`${name}: human-pass status is not fail-closed`)
  for (const phrase of banned) {
    if (md.toLowerCase().includes(phrase.toLowerCase())) failures.push(`${name}: banned/repetitive phrase remains: ${phrase}`)
  }
  if (plain !== cleanNarration) failures.push(`${name}: Markdown narration and plaintext are not synchronized`)
  const cold = sections.find((section) => ['Cold open', 'Opening'].includes(section.name))?.body?.trim()
  if (!cold) failures.push(`${name}: missing cold open`)
  else {
    const digest = crypto.createHash('sha256').update(cold).digest('hex')
    if (coldOpens.has(digest)) failures.push(`${name}: duplicated cold open`)
    coldOpens.add(digest)
  }
  const variation = humanPass.match(/## Structural variation\n\n([^\n]+)/)?.[1]?.trim()
  if (!variation) failures.push(`${name}: missing structural-variation receipt`)
  else if (variations.has(variation)) failures.push(`${name}: structural variation duplicates another video`)
  else variations.add(variation)

  for (const paragraph of cleanNarration.split(/\n\n+/)) {
    const normalized = paragraph.replace(/\s+/g, ' ').trim()
    if (wordCount(normalized) < 40) continue
    const digest = crypto.createHash('sha256').update(normalized).digest('hex')
    const owner = paragraphOwners.get(digest)
    if (owner && owner !== name) failures.push(`${name}: exact long paragraph duplicated from ${owner}`)
    paragraphOwners.set(digest, name)
  }
  results.push({ file: name, wordCount: count, status: 'humanized-owner-confirmation-required' })
}

if (!fs.existsSync(auditPath)) failures.push('Missing number-verification ledger')
else {
  const audit = JSON.parse(fs.readFileSync(auditPath, 'utf8'))
  if (!Array.isArray(audit.claims) || audit.claims.length !== 60) failures.push(`Expected 60 key-claim checks; found ${audit.claims?.length ?? 0}`)
  const unresolved = (audit.claims || []).filter((claim) => /unverified|requires|pending/i.test(claim.status || ''))
  if (unresolved.length) failures.push(`Number-verification ledger has ${unresolved.length} unresolved claims`)
  const perVideo = new Map()
  for (const claim of audit.claims || []) perVideo.set(claim.sequence, (perVideo.get(claim.sequence) || 0) + 1)
  for (let i = 1; i <= 20; i += 1) if ((perVideo.get(i) || 0) < 3) failures.push(`Video ${i}: fewer than three key claims in source audit`)
}


if (!fs.existsSync(exhaustiveAuditPath)) failures.push('Missing exhaustive number-verification ledger')
else {
  const exhaustive = JSON.parse(fs.readFileSync(exhaustiveAuditPath, 'utf8'))
  const current = []
  for (let sequence = 1; sequence <= files.length; sequence += 1) {
    const name = files[sequence - 1]
    const md = fs.readFileSync(path.join(finalDir, name), 'utf8')
    const narration = md.match(/## Narration\n([\s\S]*?)(?=\n## Human fingerprint gate)/)?.[1] || ''
    const compact = narration.replace(/^### .*$/gm, '').replace(/\s+/g, ' ').trim()
    const sentences = compact.split(/(?<=[.!?])\s+/).filter((sentence) => /\d/.test(sentence))
    for (const sentence of sentences) current.push({ sequence, sentence: sentence.trim() })
  }
  const recorded = exhaustive.sentences || []
  if (recorded.length !== current.length) failures.push(`Exhaustive number audit has ${recorded.length} entries; current scripts have ${current.length}`)
  for (let index = 0; index < Math.min(recorded.length, current.length); index += 1) {
    if (recorded[index].sequence !== current[index].sequence || recorded[index].sentence !== current[index].sentence) {
      failures.push(`Exhaustive number audit drift at occurrence ${index + 1}`)
      break
    }
    if (!Array.isArray(recorded[index].sourceUrls) || recorded[index].sourceUrls.length === 0) failures.push(`Numeric occurrence ${index + 1} has no source URL`)
    if (/unverified|requires|pending/i.test(recorded[index].status || '')) failures.push(`Numeric occurrence ${index + 1} is unresolved`)
  }
}

if (!fs.existsSync(ledgerPath)) failures.push('Missing approval ledger')
else {
  const ledger = JSON.parse(fs.readFileSync(ledgerPath, 'utf8'))
  if (ledger.length !== 20) failures.push(`Expected 20 approval records; found ${ledger.length}`)
  const falselyApproved = ledger.filter((row) => row.status === 'approved')
  if (falselyApproved.length) failures.push(`${falselyApproved.length} scripts are marked approved before owner voice/master review`)
}

if (failures.length) {
  console.error('Humanization validation failed:\n- ' + failures.join('\n- '))
  process.exit(1)
}

console.log(JSON.stringify({ scripts: results.length, keyClaims: 60, numericOccurrences: 87, ownerApprovals: 0, status: 'humanized-editorial-pass-validated' }, null, 2))
