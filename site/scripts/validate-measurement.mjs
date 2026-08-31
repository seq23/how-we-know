import fs from 'node:fs'
import { assert, assertUnique, readJson } from './validation-helpers.mjs'

const rules = readJson('content/traffic-sources.json')
const contract = readJson('data/measurement/kpi-contract.json')
const observations = readJson('data/measurement/observations.json')
const analytics = fs.readFileSync('src/components/Analytics.tsx', 'utf8')
const privacy = fs.readFileSync('src/routes/privacy.tsx', 'utf8')

assertUnique(rules.map((item) => item.id), 'traffic-source rule id')
assert(rules.filter((item) => item.category === 'ai-assistant').length >= 5, 'AI-referrer registry is too thin')
assert(contract.metrics.length === 8, 'KPI truth contract must preserve eight distinct metric classes')
assert(Array.isArray(observations), 'Measurement observations must be an array')
assert(analytics.includes('VITE_GA_MEASUREMENT_ID'), 'Analytics must remain provider-configurable')
assert(analytics.includes('traffic_source_classified'), 'Analytics must emit a separate source-classification event')
assert(privacy.includes('Some assistants and browsers suppress referrer data'), 'Privacy notice must disclose attribution limits')

console.log('Measurement and referral-classification validation passed.')
