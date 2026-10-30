/**
 * entity_backlink_watch: do the profiles in entity.json still exist, and do they point back?
 *
 * Run weekly by .github/workflows/entity-backlink-watch.yml (cron + workflow_dispatch), or by hand:
 *   node scripts/entity-backlink-watch.mjs            # fetch, classify, self-heal entity.json
 *   node scripts/entity-backlink-watch.mjs --dry-run  # fetch and classify, write nothing
 *
 * Every sameAs and profiles_pending URL is fetched with a browser user agent (three tries) and
 * given exactly one state:
 *   linked        2xx, the page is the profile (its handle/path is on it) and it names this site's host.
 *   no_linkback   2xx, the profile page, but this site's host is nowhere on it.  -> NAMED STOP (owner login)
 *   unverifiable  2xx but the platform renders client-side (Instagram, Gumroad, Google Maps, TikTok)
 *                 or the page served was an interstitial, not the profile. A named state, never a pass.
 *   dead          404 or 410 on every try.
 *   unreachable   anything else (5xx, 429, network) on every try. Not removed: a bad week is not a dead page.
 *
 * Self-heal (writes entity.json; the workflow turns the diff into a PR):
 *   - a dead sameAs URL is removed and parked in profiles_pending with a note;
 *   - a pending profile that is now `linked` is promoted into sameAs.
 *     (A pending profile is promoted only on a verified link-back: a 200 alone proves nothing on
 *     platforms that answer 200 for handles that do not exist.)
 * Rule 0: zero URLs examined exits 1. A no_linkback is a named stop printed with the exact profile
 * field to edit, and written to the report the workflow files as an issue.
 */
import fs from 'node:fs'
import { pathToFileURL } from 'node:url'

export const UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'
const CLIENT_RENDERED = /(^|\.)(instagram\.com|gumroad\.com|tiktok\.com|maps\.google\.com|maps\.app\.goo\.gl|g\.page)$/u

/** Where the owner fixes a missing link-back, per platform. */
const LINK_FIELD = {
  'youtube.com': 'YouTube Studio > Customization > Basic info > Description (the text is channel/about.md, pushed by loop/channel_about.py) and Links',
  'pinterest.com': 'Pinterest > Edit profile > Website',
  'facebook.com': 'Facebook Page > Edit Page info > Website',
  'github.com': 'GitHub > Settings > Profile > URL',
  'x.com': 'X > Edit profile > Website',
  'linkedin.com': 'LinkedIn company page > Edit page > Website URL',
}

const hostOf = (url) => new URL(url).hostname.replace(/^www\./u, '')
const urlOf = (item) => (typeof item === 'string' ? item : item.url)

/** The handle or path that must be on a page for it to be that profile and not an interstitial. */
const identityOf = (url) => {
  const segment = new URL(url).pathname.split('/').filter(Boolean).pop()
  return segment ? decodeURIComponent(segment).toLowerCase() : null
}

export async function classify(url, ownHost, fetchImpl = fetch, tries = 3) {
  let last = { status: 0, error: '' }
  for (let attempt = 0; attempt < tries; attempt += 1) {
    try {
      const res = await fetchImpl(url, { redirect: 'follow', headers: { 'user-agent': UA, 'accept-language': 'en-US,en' } })
      const body = res.ok ? await res.text() : ''
      last = { status: res.status, error: '' }
      if (res.ok) {
        const finalHost = hostOf(res.url || url)
        if (CLIENT_RENDERED.test(finalHost)) return { url, state: 'unverifiable', status: res.status, why: 'client-rendered platform' }
        const lower = body.toLowerCase()
        const identity = identityOf(url)
        if (identity && !lower.includes(identity)) {
          return { url, state: 'unverifiable', status: res.status, why: `the page served does not carry "${identity}" (interstitial or consent page)` }
        }
        return lower.includes(ownHost)
          ? { url, state: 'linked', status: res.status }
          : { url, state: 'no_linkback', status: res.status }
      }
    } catch (error) {
      last = { status: 0, error: String(error?.message ?? error) }
    }
  }
  if (last.status === 404 || last.status === 410) return { url, state: 'dead', status: last.status }
  return { url, state: 'unreachable', status: last.status, why: last.error || `HTTP ${last.status}` }
}

/** Pure: given entity.json and the classified results, the healed entity and what changed. */
export function heal(entity, results, today) {
  const byUrl = new Map(results.map((r) => [r.url, r]))
  const next = structuredClone(entity)
  const changes = []
  next.sameAs = entity.sameAs.filter((url) => {
    if (byUrl.get(url)?.state !== 'dead') return true
    changes.push(`removed dead sameAs ${url} (HTTP ${byUrl.get(url).status})`)
    next.profiles_pending.push({ url, note: `removed from sameAs ${today}: HTTP ${byUrl.get(url).status}. Promoted back when it resolves with a link-back.` })
    return false
  })
  next.profiles_pending = next.profiles_pending.filter((item) => {
    const url = urlOf(item)
    if (byUrl.get(url)?.state !== 'linked' || next.sameAs.includes(url)) return true
    changes.push(`promoted ${url} from profiles_pending into sameAs (resolves and links back)`)
    next.sameAs.push(url)
    return false
  })
  const stops = results
    .filter((r) => r.state === 'no_linkback' && entity.sameAs.includes(r.url))
    .map((r) => {
      const field = Object.entries(LINK_FIELD).find(([host]) => hostOf(r.url).endsWith(host))?.[1] ?? 'the profile\'s website field'
      return `NAMED STOP [ENTITY_LINKBACK_MISSING] (owner login) ${r.url} does not name https://${entity.url ? hostOf(entity.url) : ''}. Edit: ${field}. Clears on the next weekly run once the link is there.`
    })
  return { next, changes, stops }
}

async function main() {
  const dryRun = process.argv.includes('--dry-run')
  const file = process.env.ENTITY_FILE || 'entity.json'
  const entity = JSON.parse(fs.readFileSync(file, 'utf8'))
  const ownHost = hostOf(entity.url)
  const urls = [...entity.sameAs, ...entity.profiles_pending.map(urlOf)]
  if (!urls.length) {
    console.error('entity-backlink-watch examined zero profiles: entity.json has no sameAs and nothing pending')
    process.exit(1)
  }
  const results = []
  for (const url of urls) results.push(await classify(url, ownHost))
  const today = new Date().toISOString().slice(0, 10)
  const { next, changes, stops } = heal(entity, results, today)

  for (const r of results) console.log(`${r.state.padEnd(12)} ${r.url}${r.why ? ` (${r.why})` : ''}`)
  for (const c of changes) console.log(`SELF-HEAL ${c}`)
  for (const s of stops) console.log(s)
  if (!next.sameAs.length) {
    console.log('NAMED STOP [ENTITY_SAMEAS_EMPTY] every sameAs profile is dead; validate-entity-graph will refuse the build until one resolves.')
  }
  const report = { checked_at: new Date().toISOString(), results, changes, stops }
  if (process.env.WATCH_REPORT) fs.writeFileSync(process.env.WATCH_REPORT, `${JSON.stringify(report, null, 2)}\n`)
  if (changes.length && !dryRun) fs.writeFileSync(file, `${JSON.stringify(next, null, 2)}\n`)
  console.log(`entity-backlink-watch: ${results.length} profiles examined, ${changes.length} self-heal changes, ${stops.length} named stops.`)
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) await main()
