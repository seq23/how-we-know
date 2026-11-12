// The depth explorer's Challenger Deep number must equal its sourced value.
// The question record's keyStat is the admitted, sourced figure (NOAA and the
// 2021 submersible study); the explorer constant is compared against it, never
// against a hard-coded number. Trimmed 10 Nov 2026 (hostile review of the
// validator cut): the accessibility and markup pins were cut.
import fs from 'node:fs'
import { assert, readJson } from './validation-helpers.mjs'

const raw = readJson('content/questions.json')
const questions = Array.isArray(raw) ? raw : raw.questions || []
const record = questions.find((q) => q.slug === 'what-is-the-deepest-part-of-the-ocean')
assert(record, 'content/questions.json has no what-is-the-deepest-part-of-the-ocean record to check the explorer against')
const statText = String(record?.keyStat?.value || '')
const sourced = Number((statText.match(/([\d][\d,_]*)\s*m\b/) || [])[1]?.replace(/[,_]/g, ''))
assert(Number.isFinite(sourced) && sourced > 0, `the Challenger Deep record's keyStat "${statText}" carries no metre figure`)
assert((record?.sourceIds || []).length > 0, 'the Challenger Deep record cites no sources, so its figure is not a sourced value')

const explorer = fs.readFileSync('src/lib/explorer.ts', 'utf8')
const constant = Number((explorer.match(/CHALLENGER_DEEP_M\s*=\s*([\d_]+)/) || [])[1]?.replace(/_/g, ''))
assert(Number.isFinite(constant), 'src/lib/explorer.ts no longer defines CHALLENGER_DEEP_M')
assert(constant === sourced, `explorer CHALLENGER_DEEP_M is ${constant} m but the sourced question record says ${sourced} m`)

console.log(`Explorer depth matches its source: ${constant} m.`)
