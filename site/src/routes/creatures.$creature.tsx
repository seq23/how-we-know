import { createFileRoute, notFound } from '@tanstack/react-router'
import { getCreatureBySlug } from '~/lib/creatures-data'
import { getZoneBySlug, formatDepth } from '~/lib/ocean-data'
import { getSources } from '~/lib/sources-data'
import { SourcesList } from '~/components/SourcesList'
import { pageMeta } from '~/lib/seo'
import { breadcrumbSchema, jsonLdScript } from '~/lib/schema'

export const Route = createFileRoute('/creatures/$creature')({
  loader: ({ params }) => {
    const record = getCreatureBySlug(params.creature)
    if (!record) throw notFound()
    return record
  },
  head: ({ loaderData }) => {
    if (!loaderData) return {}
    return {
      ...pageMeta(loaderData.name, loaderData.summary, `/creatures/${loaderData.slug}`),
      scripts: [
        jsonLdScript(
          breadcrumbSchema([
            { name: 'Home', path: '/' },
            { name: 'Creatures', path: '/creatures' },
            { name: loaderData.name, path: `/creatures/${loaderData.slug}` },
          ]),
        ),
      ],
    }
  },
  component: CreaturePage,
})

function CreaturePage() {
  const creature = Route.useLoaderData()
  return (
    <main className="shell prose-page">
      <p className="eyebrow">Creature reference</p>
      <h1>{creature.name}</h1>
      <p className="dek">
        <em>{creature.scientificName}</em> · {formatDepth(creature.minDepthM, creature.maxDepthM)}
      </p>
      <section className="direct-answer">
        <p className="answer-label">Reference answer</p>
        <p>{creature.summary}</p>
      </section>
      <section>
        <h2>Adaptations</h2>
        <ol className="adaptation-list">
          {creature.adaptations.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ol>
      </section>
      <section>
        <h2>Depth zones</h2>
        <div className="mini-grid">
          {creature.zones.map((slug) => {
            const zone = getZoneBySlug(slug)
            return zone ? (
              <a key={slug} href={`/zones/${slug}`}>
                <strong>{zone.name}</strong>
                <span>{zone.summary}</span>
              </a>
            ) : null
          })}
        </div>
      </section>
      <SourcesList sources={getSources(creature.sourceIds)} />
    </main>
  )
}
