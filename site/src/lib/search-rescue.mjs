import policy from '../../content/search-rescue.json' with { type: 'json' }
export const redirects = policy.redirects
export const routeKey = (path) => path.replace(/\/$/, '') || '/'
export const isKept = (path) => !Object.hasOwn(redirects, routeKey(path))
// The final URL of a route: a retired route's target, and always the slashed form
// Cloudflare Pages serves (`/creatures/x` 308s to `/creatures/x/`). Internal links
// to the slashless form are what Search Console reported as "Page with redirect"
// on the site's top pages (Search Readiness o1, 5 Nov 2026).
export const slashed = (path) => {
  const m = String(path).match(/^([^?#]*)(.*)$/)
  const [p, rest] = [m[1], m[2]]
  return p.endsWith('/') || /\.[a-z0-9]+$/i.test(p) ? `${p}${rest}` : `${p}/${rest}`
}
export const canonicalPath = (path) => slashed(redirects[routeKey(path)] ?? path)
export const keptQuestions = (records) => records.filter((r) => isKept(`/questions/${r.slug}`))
export const keptCreatures = (records) => records.filter((r) => isKept(`/creatures/${r.slug}`))
// Fold the source material into the surviving answer rather than discarding it.
export function consolidateQuestions(records, creatures) {
  return keptQuestions(records).map((record) => {
    const target = `/questions/${record.slug}/`
    const donors = records.filter((r) => redirects[`/questions/${r.slug}`] === target)
    const references = creatures.filter((r) => redirects[`/creatures/${r.slug}`] === target)
    return { ...record,
      reviewedAt: donors.length || references.length ? policy.reviewedAt : record.reviewedAt,
      sections: [...record.sections, ...donors.flatMap((r) => r.sections),
        ...references.map((r) => ({heading: `What adaptations does ${r.name.toLowerCase()} have?`, paragraphs: [r.summary, ...r.adaptations]}))],
      sourceIds: [...new Set([...record.sourceIds, ...donors.flatMap((r) => r.sourceIds), ...references.flatMap((r) => r.sourceIds)])],
    }
  })
}
