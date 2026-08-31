import { createFileRoute } from '@tanstack/react-router'
import { activeMethods } from '~/lib/method-index'
import { pageMeta } from '~/lib/seo'

export const Route = createFileRoute('/methods/')({
  head: () =>
    pageMeta(
      'How we know it',
      'Every answer on this site is grouped by the kind of evidence behind it — measured by an instrument, inferred from a proxy, observed once, or reconstructed from fragments.',
      '/methods',
    ),
  component: MethodsIndex,
})

function MethodsIndex() {
  return (
    <main className="shell index-page">
      <header className="index-hero">
        <p className="eyebrow">Evidence index</p>
        <h1>How we know it.</h1>
        <p>
          A subject tells you what a page is about. A method tells you what kind of evidence stands
          behind it, and how far that evidence reaches. The same handful of methods recur no matter
          what the question is about.
        </p>
      </header>
      <div className="card-grid">
        {activeMethods.map((entry) => (
          <a className="question-card" key={entry.id} href={`/methods/${entry.id}`}>
            <span>
              {entry.pages.length} {entry.pages.length === 1 ? 'answer' : 'answers'}
            </span>
            <h2>{entry.name}</h2>
            <p>{entry.blurb}</p>
          </a>
        ))}
      </div>
    </main>
  )
}
