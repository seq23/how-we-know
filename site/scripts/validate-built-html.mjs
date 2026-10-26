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

const failures = []
const titles = new Map()
const descriptions = new Map()
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
  if (title.length < 30 || title.length > 65) failures.push(`${where}: title is ${title.length} characters`)
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

  offers += deepNodes(nodes).filter(
    (node) =>
      /^(SoftwareApplication|WebApplication|MobileApplication|Product|Service|Course|Book)$/u.test(typesOf(node)[0] ?? '') &&
      deepNodes(node).some((child) => /^(Offer|AggregateOffer)$/u.test(typesOf(child)[0] ?? '') && child.price !== undefined),
  ).length
}

if (!offers) failures.push('no Product, Service or SoftwareApplication with a priced Offer on any page')

assert(examined > 0, 'Built-HTML validation examined zero pages')
assert(failures.length === 0, `Built HTML is not search-ready:\n  ${failures.join('\n  ')}`)
console.log(`Built-HTML validation passed (${examined} pages: titles, descriptions, social tags, Organization, WebPage, breadcrumbs, priced Offer).`)
