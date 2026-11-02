import { referencePage } from '~/lib/reference-page'
import { jsonLdScript } from '~/lib/schema'
import { PublisherLine } from '~/components/PublisherLine'
import { ReferenceDetails } from '~/components/ReferenceDetails'
import { redirects } from '~/lib/search-rescue.mjs'
import { createFileRoute, notFound, redirect } from '@tanstack/react-router'
import { getCreatureBySlug } from '~/lib/creatures-data'
import { getZoneBySlug, formatDepth } from '~/lib/ocean-data'
import { getSources } from '~/lib/sources-data'
import { SourcesList } from '~/components/SourcesList'
import { pageMeta } from '~/lib/seo'

export const Route = createFileRoute('/creatures/$creature')({
  loader: ({ params }) => {
    const target = redirects[`/creatures/${params.creature}`]
    if (target) throw redirect({ href: target, statusCode: 301 })
    const record = getCreatureBySlug(params.creature)
    if (!record) throw notFound()
    return record
  },
  head: ({ loaderData }) => {
    if (!loaderData) return {}
    const meta = pageMeta(loaderData.name, loaderData.summary, `/creatures/${loaderData.slug}`)
    return { ...meta, scripts: [...meta.scripts, ...referencePage(loaderData, 'creature').schemas.map(jsonLdScript)] }
  },
  component: CreaturePage,
})

function CreaturePage() {
  const creature = Route.useLoaderData()
  return (
    <main className="shell prose-page">
      <p className="eyebrow">Creature reference</p>
      <h1>{creature.name}</h1>
      <p className="definition">{referencePage(creature, 'creature').definition}</p>
      <PublisherLine publishedAt="2026-08-31" updatedAt="2026-11-02" />
      <p className="dek">
        <em>{creature.scientificName}</em> · {formatDepth(creature.minDepthM, creature.maxDepthM)}
      </p>
      <section className="direct-answer">
        <h2>Quick answer</h2>
        <p>{creature.summary}</p>
      </section>
      <section>
        <h2>What adaptations help this animal survive?</h2>
        <ol className="adaptation-list">
          {creature.adaptations.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ol>
      </section>
      <section>
        <h2>Which ocean zones does it inhabit?</h2>
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
      <ReferenceDetails record={creature} kind="creature" />
      <SourcesList sources={getSources(creature.sourceIds)} />
    </main>
  )
}
