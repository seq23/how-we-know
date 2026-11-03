import { PublisherLine, NextStep } from '~/components/PublisherLine'
import { jsonLdScript } from '~/lib/schema'
import { createFileRoute, notFound } from '@tanstack/react-router'
import { getMethodEntry } from '~/lib/method-index'
import { getSubject } from '~/lib/taxonomy'
import { pageMeta } from '~/lib/seo'

export const Route = createFileRoute('/methods/$method')({
  loader: ({ params }) => {
    const entry = getMethodEntry(params.method)
    if (!entry) throw notFound()
    return entry
  },
  head: ({ loaderData }) => {
    if (!loaderData) return {}
    const meta = pageMeta(loaderData.name, loaderData.blurb, `/methods/${loaderData.id}`)
    return { ...meta, scripts: [...meta.scripts, jsonLdScript({ '@context': 'https://schema.org', '@type': 'FAQPage', mainEntity: methodFaqs(loaderData.name, loaderData.blurb).map(f => ({ '@type': 'Question', name: f.question, acceptedAnswer: { '@type': 'Answer', text: f.answer } })), speakable: { '@type': 'SpeakableSpecification', cssSelector: ['.definition', '#faq'] } })] }
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
        <p className="definition">{entry.blurb} This evidence index groups answers by how their claims were established. Follow an individual question to see its sources, comparison, uncertainties and the distinction between a measured result and the interpretation built from it.</p>
        <PublisherLine publishedAt="2026-08-31" updatedAt="2026-11-02" />
      </header>
      <h2>Which answers use this evidence?</h2>
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
      <section id="faq"><h2>Frequently asked questions</h2>{methodFaqs(entry.name, entry.blurb).map(f => <section key={f.question}><h3>{f.question}</h3><p>{f.answer}</p></section>)}</section>
      <NextStep kind="method" slug={entry.id} />
    </main>
  )
}

function methodFaqs(name: string, blurb: string) {
  return [
    { question: `What does ${name.toLowerCase()} mean?`, answer: `${blurb} The label identifies the evidence used for an answer, rather than certifying every possible interpretation. Open the linked question to see the particular observation or source, and the limits the article places on its conclusion.` },
    { question: 'Does an evidence label establish certainty?', answer: 'No. A label describes how evidence was obtained. An instrument can have uncertainty, an observation can be genuine but unrepresentative, and a reconstruction can leave missing pieces. Each linked answer supplies its own context; the method alone does not establish how widely a result applies.' },
    { question: 'Where are the original sources?', answer: 'Open any answer listed above and follow its Sources reviewed section. That list names the original organizations and links their accounts. The answer also distinguishes the fact being reported from the interpretation of it, so readers can check the evidence rather than relying on this index alone.' },
  ]
}
