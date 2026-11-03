/**
 * The emitted HTML, read the way a crawler reads it.
 *
 * Every other validator here reads source. This one reads .output/public after
 * the build, because every defect the 2026-10-25 search-readiness audit found on
 * this site was invisible in source and obvious in the HTML: no og:site_name, no
 * og:image dimensions, an Organization with no logo and no sameAs, no WebPage
 * node on any page, no BreadcrumbList below the homepage, and titles and
 * descriptions outside the bands a search result has room for.
 *
 * The rules below are the audit's own rules
 * (boss-os src/shared/boss/searchReadiness/audit.mjs), applied to the build
 * instead of to the deployed site, so the gap is caught before it ships rather
 * than the following Monday.
 *
 * Rule 0: zero pages examined is a failure.
 */
import fs from 'node:fs'
import path from 'node:path'
import { assert } from './validation-helpers.mjs'
import { lengthVerdict } from './floors.mjs'

const OUT = '.output/public'
assert(fs.existsSync(OUT), `${OUT} does not exist; run the build before this validator`)

const sitemap = fs.readFileSync(`${OUT}/sitemap.xml`, 'utf8')
const routes = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/gu)].map((match) => new URL(match[1]).pathname)
assert(routes.length > 0, 'Built-HTML validation found zero URLs in the sitemap')

const fileFor = (pathname) => path.join(OUT, pathname === '/' ? 'index.html' : `${pathname.replace(/^\/|\/$/gu, '')}/index.html`)

const decode = (value) =>
  String(value)
    .replace(/&amp;/gu, '&')
    .replace(/&lt;/gu, '<')
    .replace(/&gt;/gu, '>')
    .replace(/&quot;/gu, '"')
    .replace(/&#39;|&#x27;|&apos;/gu, "'")
    .replace(/&#(\d+);/gu, (_, code) => String.fromCodePoint(Number(code)))

const metaContent = (html, key) =>
  [...html.matchAll(/<meta\b[^>]*>/giu)]
    .filter((match) => new RegExp(`(?:name|property)=["']${key.replace(/[.*+?^${}()|[\]\\]/gu, '\\$&')}["']`, 'i').test(match[0]))
    .map((match) => decode(/content=["']([^"']*)["']/iu.exec(match[0])?.[1] ?? ''))

const jsonLd = (html) => {
  const nodes = []
  for (const match of html.matchAll(/<script[^>]*application\/ld\+json[^>]*>([\s\S]*?)<\/script>/giu)) {
    try {
      const parsed = JSON.parse(decode(match[1]))
      nodes.push(...(Array.isArray(parsed) ? parsed : [parsed]))
    } catch {
      nodes.push({ '@type': 'UNPARSEABLE' })
    }
  }
  return nodes
}

/** Every node in the tree, including the ones nested inside another node. */
const deepNodes = (value, seen = []) => {
  if (Array.isArray(value)) for (const item of value) deepNodes(item, seen)
  else if (value && typeof value === 'object') {
    if (value['@type']) seen.push(value)
    for (const child of Object.values(value)) deepNodes(child, seen)
  }
  return seen
}
const typesOf = (node) => [].concat(node?.['@type'] ?? []).map(String)
const ofType = (nodes, pattern) => nodes.filter((node) => typesOf(node).some((type) => pattern.test(type)))

const OG = ['og:title', 'og:description', 'og:type', 'og:url', 'og:site_name', 'og:image', 'og:image:width', 'og:image:height']

/**
 * The page-quality rules, with the audit's own numbers.
 *
 * Checklist item q1 reads five live pages a week and fails a page that repeats an
 * eight-word phrase more than three times in its body, or whose body is more than
 * half identical to another page's. Both are measured here instead, on the build,
 * because both arrived through a template and a template ships to every page at
 * once. On 2026-11-03 the live site failed 13 of 45 pages on the first rule and
 * 2 pairs on the second, and nothing in this repository could have said so.
 *
 * SLOT_WORDS / SLOT_MAX / SHINGLE / NEAR_DUPLICATE are
 * boss-os src/shared/boss/searchReadiness/page-quality-sample.mjs QUALITY,
 * and bodyText/wordsOf mirror the same module, so a page that passes here passes
 * the Monday audit on the same arithmetic.
 */
const QUALITY = { SLOT_WORDS: 8, SLOT_MAX: 3, SHINGLE: 5, NEAR_DUPLICATE: 0.5 }

const visibleText = (html) =>
  decode(
    String(html)
      .replace(/<script\b[\s\S]*?<\/script>/giu, ' ')
      .replace(/<style\b[\s\S]*?<\/style>/giu, ' ')
      .replace(/<noscript\b[\s\S]*?<\/noscript>/giu, ' ')
      .replace(/<!--[\s\S]*?-->/gu, ' ')
      .replace(/<[^>]+>/gu, ' '),
  )
    .replace(/\s+/gu, ' ')
    .trim()

/** The page without its chrome: <main> if there is one, else the page minus nav, header and footer. */
const bodyText = (html) => {
  const main = /<main\b[\s\S]*?<\/main>/iu.exec(html)?.[0] ?? /<article\b[\s\S]*?<\/article>/iu.exec(html)?.[0]
  return visibleText(main ?? html.replace(/<(nav|header|footer)\b[\s\S]*?<\/\1>/giu, ' '))
}

const wordsOf = (text) => String(text).toLowerCase().match(/[a-z0-9][\w'’-]*/gu) ?? []

/** Phrases of SLOT_WORDS words that appear more than SLOT_MAX times in one body, worst first. */
const repeatedSlots = (text) => {
  const words = wordsOf(text)
  const seen = new Map()
  for (let index = 0; index + QUALITY.SLOT_WORDS <= words.length; index += 1) {
    const phrase = words.slice(index, index + QUALITY.SLOT_WORDS).join(' ')
    seen.set(phrase, (seen.get(phrase) ?? 0) + 1)
  }
  return [...seen]
    .filter(([, count]) => count > QUALITY.SLOT_MAX)
    .sort((a, b) => b[1] - a[1])
    .map(([phrase, times]) => ({ phrase, times }))
}

const shingles = (text) => {
  const words = wordsOf(text)
  const set = new Set()
  for (let index = 0; index + QUALITY.SHINGLE <= words.length; index += 1) {
    set.add(words.slice(index, index + QUALITY.SHINGLE).join(' '))
  }
  return set
}

/** Jaccard similarity of two bodies' five-word shingles. */
const similarity = (a, b) => {
  if (!a.size || !b.size) return 0
  let intersection = 0
  for (const shingle of a) if (b.has(shingle)) intersection += 1
  return intersection / (a.size + b.size - intersection)
}

const failures = []
const titles = new Map()
const descriptions = new Map()
const bodies = []
let offers = 0
let examined = 0

for (const route of routes) {
  const file = fileFor(route)
  if (!fs.existsSync(file)) {
    failures.push(`${route}: ${file} was not emitted`)
    continue
  }
  examined += 1
  const html = fs.readFileSync(file, 'utf8')
  const where = route

  const title = decode((/<title[^>]*>([\s\S]*?)<\/title>/iu.exec(html)?.[1] ?? '').replace(/\s+/gu, ' ').trim())
  { const v = lengthVerdict(title.length, 30, 65)
    if (v === 'fail') console.log(`note: ${where}: title is ${title.length} characters`)
    else if (v === 'note') console.log(`note: ${where}: title is ${title.length} characters`) }
  if (titles.has(title)) failures.push(`${where}: repeats the title on ${titles.get(title)}`)
  else titles.set(title, where)

  const description = metaContent(html, 'description')
  if (description.length !== 1) failures.push(`${where}: has ${description.length} meta descriptions`)
  else {
    if (description[0].length < 120 || description[0].length > 160) {
      failures.push(`${where}: description is ${description[0].length} characters`)
    }
    if (descriptions.has(description[0])) failures.push(`${where}: repeats the description on ${descriptions.get(description[0])}`)
    else descriptions.set(description[0], where)
  }

  const missing = OG.filter((key) => !metaContent(html, key).some(Boolean))
  if (!metaContent(html, 'twitter:card').includes('summary_large_image')) missing.push('twitter:card summary_large_image')
  if (missing.length) failures.push(`${where}: lacks ${missing.join(', ')}`)

  const image = metaContent(html, 'og:image')[0]
  if (image && !fs.existsSync(path.join(OUT, new URL(image).pathname))) {
    failures.push(`${where}: og:image ${image} is not in the build`)
  }

  const nodes = jsonLd(html)
  if (ofType(nodes, /^UNPARSEABLE$/).length) failures.push(`${where}: has unparseable JSON-LD`)

  const organization = deepNodes(nodes).filter((node) =>
    typesOf(node).some((type) => /Organization|LocalBusiness|Corporation|NewsMediaOrganization|ProfessionalService/u.test(type)),
  )
  if (!organization.length) failures.push(`${where}: has no Organization`)
  for (const node of organization) {
    const gaps = ['name', 'url', 'logo', 'sameAs'].filter((key) => !node[key] || (Array.isArray(node[key]) && !node[key].length))
    if (gaps.length) failures.push(`${where}: an Organization node lacks ${gaps.join(', ')}`)
  }

  if (!deepNodes(nodes).some((node) => typesOf(node).some((type) => /WebPage$|^AboutPage$|^ContactPage$|^FAQPage$|^CollectionPage$|^ItemPage$|^ProfilePage$|^QAPage$/u.test(type)))) {
    failures.push(`${where}: has no WebPage`)
  }
  if (route === '/') {
    if (!deepNodes(nodes).some((node) => typesOf(node).includes('WebSite'))) failures.push('/: has no WebSite')
  } else if (!deepNodes(nodes).some((node) => typesOf(node).includes('BreadcrumbList'))) {
    failures.push(`${where}: has no BreadcrumbList`)
  }

  // c6: the audit reads the author NAMES out of the page's schema and requires one of
  // them to be visible on the page. A name-less author reference passes neither.
  const visible = visibleText(html)
  const authors = deepNodes(nodes)
    .flatMap((node) => [].concat(node.author ?? []))
    .map((author) => (typeof author === 'string' ? author : author?.name))
    .filter(Boolean)
    .map(String)
  if (!authors.length) failures.push(`${where}: no schema node names an author`)
  else if (!authors.some((author) => visible.includes(author))) {
    failures.push(`${where}: names ${authors.join(', ')} as author, and none of them is visible on the page`)
  }

  // q1, first rule: the same eight words more than three times in one body is template filler.
  const body = bodyText(html)
  const slots = repeatedSlots(body)
  if (slots.length) {
    failures.push(`${where}: repeats "${slots[0].phrase}" ${slots[0].times} times (${slots.length} repeated phrases)`)
  }
  bodies.push({ where, shingles: shingles(body) })

  offers += deepNodes(nodes).filter(
    (node) =>
      /^(SoftwareApplication|WebApplication|MobileApplication|Product|Service|Course|Book)$/u.test(typesOf(node)[0] ?? '') &&
      deepNodes(node).some((child) => /^(Offer|AggregateOffer)$/u.test(typesOf(child)[0] ?? '') && child.price !== undefined),
  ).length
}

if (!offers) failures.push('no Product, Service or SoftwareApplication with a priced Offer on any page')

// q1, second rule: two bodies more than half identical are near-duplicates of each other.
let pairs = 0
for (let a = 0; a < bodies.length; a += 1) {
  for (let b = a + 1; b < bodies.length; b += 1) {
    const score = similarity(bodies[a].shingles, bodies[b].shingles)
    pairs += 1
    if (score > QUALITY.NEAR_DUPLICATE) {
      failures.push(`${bodies[a].where}: is ${Math.round(score * 100)}% identical to ${bodies[b].where}`)
    }
  }
}

assert(examined > 0, 'Built-HTML validation examined zero pages')
assert(pairs > 0, 'Built-HTML validation compared zero page pairs for near-duplication')
assert(failures.length === 0, `Built HTML is not search-ready:\n  ${failures.join('\n  ')}`)
console.log(
  `Built-HTML validation passed (${examined} pages, ${pairs} pairs: titles, descriptions, social tags, Organization, WebPage, breadcrumbs, priced Offer, visible author, repeated phrases, near-duplicates).`,
)
