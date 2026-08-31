import fs from 'node:fs'
import { assert, readJson } from './validation-helpers.mjs'

const zones = readJson('content/zones.json')
const creatures = readJson('content/creatures.json')
const explorer = fs.readFileSync('src/lib/explorer.ts', 'utf8')
const component = fs.readFileSync('src/components/DepthExplorer.tsx', 'utf8')
const route = fs.readFileSync('src/routes/explore.tsx', 'utf8')

assert(explorer.includes('CHALLENGER_DEEP_M = 10_935'), 'Explorer must use the admitted Challenger Deep depth')
assert(component.includes('explorer-viewport'), 'Explorer viewport is missing')
assert(component.includes('type="range"'), 'Explorer needs a keyboard-accessible depth control')
assert(component.includes('prefers-reduced-motion'), 'Explorer must respect reduced-motion preferences')
assert(route.includes('/questions/what-is-the-deepest-part-of-the-ocean'), 'Explorer must link to the canonical Challenger Deep answer')
for (const zone of zones) assert(explorer.includes("oceanZones"), `Explorer data layer missing zone integration for ${zone.slug}`)
for (const creature of creatures) assert(component.includes('explorerCreatures'), `Explorer creature layer missing ${creature.slug}`)

console.log('Interactive depth-explorer validation passed.')
