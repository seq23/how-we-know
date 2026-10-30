/**
 * validate_entity_graph: the emitted JSON-LD says exactly what entity.json says.
 *
 * The authority audit of 30 Oct 2026 found no repo in the grid with any check
 * that its sameAs list was the one it meant to publish, and no record of who the
 * parent organisation was. entity.json is now the one definition; this check is
 * what makes it govern something.
 *
 *   node scripts/validate-entity-graph.mjs           entity.json only (also run by validate-all)
 *   node scripts/validate-entity-graph.mjs --built   entity.json AND every built page (after vite build)
 *
 * Source rules (entity.json):
 *   - @id, name, url, logo, description present; sameAs a non-empty list of https URLs, no duplicates;
 *   - no sameAs URL on the site's own host (a self-reference is not a second profile);
 *   - nothing in both sameAs and profiles_pending;
 *   - parentOrganization is Spry Labs' entity home.
 * Built rules (every page in the sitemap):
 *   - the Organization node with entity.json's @id carries sameAs EQUAL to entity.json's (same set),
 *     no self-host sameAs, and name, description, logo URL and parentOrganization @id equal to it.
 *
 * Rule 0: zero pages, or zero Organization nodes carrying the entity's @id, is a failure.
 * ENTITY_FILE and BUILT_DIR override the paths (tests/entity-graph.test.mjs uses them to prove the
 * check fails on a planted break).
 */
import fs from 'node:fs'
import path from 'node:path'
import { assert, isHttpsUrl } from './validation-helpers.mjs'

const ENTITY_FILE = process.env.ENTITY_FILE || 'entity.json'
const OUT = process.env.BUILT_DIR || '.output/public'
const SPRY_LABS_ID = 'https://billionairehighperformancecoach.com/spry-labs#organization'

const entity = JSON.parse(fs.readFileSync(ENTITY_FILE, 'utf8'))
const failures = []
const hostOf = (value) => {
  try {
    return new URL(value).hostname.replace(/^www\./u, '')
  } catch {
    return ''
  }
}
const ownHost = hostOf(entity.url)

for (const key of ['@id', 'name', 'url', 'logo', 'description']) {
  if (typeof entity[key] !== 'string' || !entity[key].trim()) failures.push(`entity.json: ${key} is missing`)
}
if (!ownHost) failures.push('entity.json: url is not a URL')
const sameAs = Array.isArray(entity.sameAs) ? entity.sameAs : []
const pending = Array.isArray(entity.profiles_pending) ? entity.profiles_pending : null
if (!sameAs.length) failures.push('entity.json: sameAs is empty (zero profiles examined)')
if (pending === null) failures.push('entity.json: profiles_pending must be a list (empty when nothing is pending)')
for (const url of sameAs) {
  if (!isHttpsUrl(url)) failures.push(`entity.json: sameAs ${url} is not an https URL`)
  if (hostOf(url) === ownHost) failures.push(`entity.json: sameAs ${url} is on the site's own host`)
}
if (new Set(sameAs).size !== sameAs.length) failures.push('entity.json: sameAs has duplicates')
for (const item of pending ?? []) {
  const url = typeof item === 'string' ? item : item?.url
  if (!isHttpsUrl(url)) failures.push(`entity.json: profiles_pending entry ${JSON.stringify(item)} has no https url`)
  if (sameAs.includes(url)) failures.push(`entity.json: ${url} is in both sameAs and profiles_pending`)
}
if (entity.parentOrganization?.['@id'] !== SPRY_LABS_ID) {
  failures.push(`entity.json: parentOrganization @id is ${entity.parentOrganization?.['@id']}, not ${SPRY_LABS_ID}`)
}

let pages = 0
let matched = 0
if (process.argv.includes('--built')) {
  assert(fs.existsSync(OUT), `${OUT} does not exist; run the build before validate-entity-graph --built`)
  const sitemap = fs.readFileSync(path.join(OUT, 'sitemap.xml'), 'utf8')
  const routes = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/gu)].map((m) => new URL(m[1]).pathname)
  const fileFor = (p) => path.join(OUT, p === '/' ? 'index.html' : `${p.replace(/^\/|\/$/gu, '')}/index.html`)
  const decode = (v) =>
    String(v)
      .replace(/&quot;/gu, '"')
      .replace(/&#39;|&#x27;|&apos;/gu, "'")
      .replace(/&lt;/gu, '<')
      .replace(/&gt;/gu, '>')
      .replace(/&amp;/gu, '&')
  const walk = (value, seen = []) => {
    if (Array.isArray(value)) for (const item of value) walk(item, seen)
    else if (value && typeof value === 'object') {
      seen.push(value)
      for (const child of Object.values(value)) walk(child, seen)
    }
    return seen
  }
  const wanted = [...sameAs].sort()
  for (const route of routes) {
    const file = fileFor(route)
    if (!fs.existsSync(file)) continue // validate-built-html names missing pages
    pages += 1
    const html = fs.readFileSync(file, 'utf8')
    for (const block of html.matchAll(/<script[^>]*application\/ld\+json[^>]*>([\s\S]*?)<\/script>/giu)) {
      let parsed
      try {
        parsed = JSON.parse(decode(block[1]))
      } catch {
        continue // validate-built-html names unparseable JSON-LD
      }
      for (const node of walk(parsed)) {
        if (node['@id'] !== entity['@id'] || !node.name) continue
        matched += 1
        const got = [].concat(node.sameAs ?? []).sort()
        if (JSON.stringify(got) !== JSON.stringify(wanted)) {
          failures.push(`${route}: Organization sameAs ${JSON.stringify(got)} != entity.json ${JSON.stringify(wanted)}`)
        }
        for (const url of got) if (hostOf(url) === ownHost) failures.push(`${route}: sameAs ${url} is a self-reference`)
        if (node.name !== entity.name) failures.push(`${route}: Organization name "${node.name}" != entity.json`)
        if (node.description !== entity.description) failures.push(`${route}: Organization description differs from entity.json`)
        const logo = typeof node.logo === 'string' ? node.logo : node.logo?.url
        if (logo !== entity.logo) failures.push(`${route}: Organization logo ${logo} != entity.json ${entity.logo}`)
        if (node.parentOrganization?.['@id'] !== entity.parentOrganization?.['@id']) {
          failures.push(`${route}: Organization parentOrganization ${node.parentOrganization?.['@id']} != entity.json`)
        }
      }
    }
  }
  if (!pages) failures.push('validate-entity-graph examined zero built pages')
  if (!matched) failures.push(`validate-entity-graph found zero Organization nodes with @id ${entity['@id']}`)
}

assert(failures.length === 0, `Entity graph drift:\n  ${failures.slice(0, 20).join('\n  ')}${failures.length > 20 ? `\n  ...and ${failures.length - 20} more` : ''}`)
console.log(
  process.argv.includes('--built')
    ? `Entity graph matches entity.json (${matched} Organization nodes on ${pages} pages; sameAs ${sameAs.length}, parent Spry Labs).`
    : `entity.json is well-formed (sameAs ${sameAs.length}, pending ${pending.length}, parent Spry Labs).`,
)
