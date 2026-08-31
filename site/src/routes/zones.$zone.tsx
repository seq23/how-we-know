import { createFileRoute, notFound } from '@tanstack/react-router'
import { getZoneBySlug, formatDepth } from '~/lib/ocean-data'
import { creatures } from '~/lib/creatures-data'
import { getSources } from '~/lib/sources-data'
import { SourcesList } from '~/components/SourcesList'
import { pageMeta } from '~/lib/seo'
import { breadcrumbSchema, jsonLdScript } from '~/lib/schema'

export const Route = createFileRoute('/zones/$zone')({
  loader: ({ params }) => {
    const record = getZoneBySlug(params.zone)
    if (!record) throw notFound()
    return record
  },
  head: ({ loaderData }) => {
    if (!loaderData) return {}
    return {
      ...pageMeta(
        `${loaderData.name} (${loaderData.scientificName})`,
        loaderData.summary,
        `/zones/${loaderData.slug}`,
      ),
      scripts: [
        jsonLdScript(
          breadcrumbSchema([
            { name: 'Home', path: '/' },
            { name: 'Zones', path: '/zones' },
            { name: loaderData.name, path: `/zones/${loaderData.slug}` },
          ]),
        ),
      ],
    }
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
      <p className="dek">
        {zone.scientificName} · {formatDepth(zone.minDepthM, zone.maxDepthM)}
      </p>
      <section className="direct-answer">
        <p className="answer-label">Reference answer</p>
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
        <h2>Defining conditions</h2>
        <ul>
          {zone.conditions.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>
      <section>
        <h2>Representative creatures</h2>
        <div className="mini-grid">
          {residents.length ? (
            residents.map((item) => (
              <a key={item.slug} href={`/creatures/${item.slug}`}>
                <strong>{item.name}</strong>
                <span>{item.summary}</span>
              </a>
            ))
          ) : (
            <p>No creature record in the initial library is restricted to this zone.</p>
          )}
        </div>
      </section>
      <SourcesList sources={getSources(zone.sourceIds)} />
    </main>
  )
}
