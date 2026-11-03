import { referencePage } from '~/lib/reference-page'
import { jsonLdScript } from '~/lib/schema'
import { PublisherLine } from '~/components/PublisherLine'
import { ReferenceDetails } from '~/components/ReferenceDetails'
import { canonicalPath } from '~/lib/search-rescue.mjs'
import { createFileRoute, notFound } from '@tanstack/react-router'
import { getZoneBySlug, formatDepth } from '~/lib/ocean-data'
import { creatures } from '~/lib/creatures-data'
import { getSources } from '~/lib/sources-data'
import { SourcesList } from '~/components/SourcesList'
import { pageMeta } from '~/lib/seo'

export const Route = createFileRoute('/zones/$zone')({
  loader: ({ params }) => {
    const record = getZoneBySlug(params.zone)
    if (!record) throw notFound()
    return record
  },
  head: ({ loaderData }) => {
    if (!loaderData) return {}
    const meta = pageMeta(
      `${loaderData.name} (${loaderData.scientificName})`,
      loaderData.summary,
      `/zones/${loaderData.slug}`,
    )
    return { ...meta, scripts: [...meta.scripts, ...referencePage(loaderData, 'zone').schemas.map(jsonLdScript)] }
  },
  component: ZonePage,
})

function ZonePage() {
  const zone = Route.useLoaderData()
  const residents = creatures.filter((item) => item.zones.includes(zone.slug))
  return (
    <main className="shell prose-page">
      <p className="eyebrow">Ocean zone</p>
      <h1>{zone.name}</h1>
      <p className="definition">{referencePage(zone, 'zone').definition}</p>
      <PublisherLine publishedAt="2026-08-31" updatedAt="2026-11-02" />
      <p className="dek">
        {zone.scientificName} · {formatDepth(zone.minDepthM, zone.maxDepthM)}
      </p>
      <section className="direct-answer">
        <h2>Quick answer</h2>
        <p>{zone.summary}</p>
      </section>
      <div className="metrics-grid">
        <div>
          <span>Light</span>
          <strong>{zone.light}</strong>
        </div>
        <div>
          <span>Temperature</span>
          <strong>{zone.temperature}</strong>
        </div>
        <div>
          <span>Pressure at base</span>
          <strong>≈ {zone.pressureAtBaseAtm} atm</strong>
        </div>
      </div>
      <section>
        <h2>What conditions define this zone?</h2>
        <ul>
          {zone.conditions.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>
      <section>
        <h2>Which animals live in this zone?</h2>
        <div className="mini-grid">
          {residents.length ? (
            residents.map((item) => (
              <a key={item.slug} href={canonicalPath(`/creatures/${item.slug}`)}>
                <strong>{item.name}</strong>
                <span>
                  {item.scientificName} · {formatDepth(item.minDepthM, item.maxDepthM)}
                </span>
              </a>
            ))
          ) : (
            <p>No creature record in the initial library is restricted to this zone.</p>
          )}
        </div>
      </section>
      <ReferenceDetails record={zone} kind="zone" />
      <SourcesList sources={getSources(zone.sourceIds)} />
    </main>
  )
}
