import { createFileRoute, notFound } from '@tanstack/react-router'
import { getMethodEntry } from '~/lib/method-index'
import { getSubject } from '~/lib/taxonomy'
import { pageMeta } from '~/lib/seo'
import { breadcrumbSchema, jsonLdScript } from '~/lib/schema'

export const Route = createFileRoute('/methods/$method')({
  loader: ({ params }) => {
    const entry = getMethodEntry(params.method)
    if (!entry) throw notFound()
    return entry
  },
  head: ({ loaderData }) => {
    if (!loaderData) return {}
    return {
      ...pageMeta(loaderData.name, loaderData.blurb, `/methods/${loaderData.id}`),
      scripts: [
        jsonLdScript(
          breadcrumbSchema([
            { name: 'Home', path: '/' },
            { name: 'How we know it', path: '/methods' },
            { name: loaderData.name, path: `/methods/${loaderData.id}` },
          ]),
        ),
      ],
    }
  },
  component: MethodPage,
})

function MethodPage() {
  const entry = Route.useLoaderData()
  return (
    <main className="shell index-page">
      <header className="index-hero">
        <p className="eyebrow">Evidence type</p>
        <h1>{entry.name}</h1>
        <p>{entry.blurb}</p>
      </header>
      <div className="card-grid">
        {entry.pages.map((item) => {
          const subject = getSubject(item.subject)
          return (
            <a className="question-card" key={item.slug} href={`/questions/${item.slug}`}>
              <span>{subject ? subject.name : item.subject}</span>
              <h2>{item.question}</h2>
              <p>{item.directAnswer}</p>
            </a>
          )
        })}
      </div>
    </main>
  )
}
