import type { QuestionPageRecord } from '~/lib/types'
import { getSources, sourceById } from '~/lib/sources-data'
import { getZoneBySlug } from '~/lib/ocean-data'
import { getCreatureBySlug } from '~/lib/creatures-data'
import { canonicalPath } from '~/lib/search-rescue.mjs'
import { getMethod, getSubject } from '~/lib/taxonomy'
import { DirectAnswer } from './DirectAnswer'
import { KeyStat } from './KeyStat'
import { ComparisonTable } from './ComparisonTable'
import { SourcesList } from './SourcesList'
import { VideoPanel } from './VideoPanel'
import { PublisherLine, NextStep } from './PublisherLine'

export function QuestionPage({ record }: { record: QuestionPageRecord }) {
  const statSource = sourceById.get(record.keyStat.sourceId)
  const subject = getSubject(record.subject)
  const method = getMethod(record.method)
  return <main>
    <header className="article-hero">
      <div className="shell article-hero-grid">
        <div>
          <p className="eyebrow">{subject?.name ?? 'Question'}</p>
          <h1>{record.question}</h1>
          <DirectAnswer>{record.directAnswer}</DirectAnswer>
          <PublisherLine publishedAt={record.publishedAt} updatedAt={record.reviewedAt} />
        </div>
        <div className="depth-orb" aria-hidden="true"><span>200 m</span><span>1,000 m</span><span>4,000 m</span><span>11,000 m</span></div>
      </div>
    </header>
    <div className="shell article-grid">
      <article className="article-body">
        <h2>What does this guide cover?</h2>
        <p>{record.description}</p>
        {statSource && <KeyStat value={record.keyStat.value} label={record.keyStat.label} sourceName={statSource.organization} sourceUrl={statSource.url} sourceCheckedAt={statSource.checkedAt} />}
        {record.sections.map(section => <section key={section.heading}>
          <h2>{section.heading}</h2>
          {section.paragraphs.map(paragraph => <p key={paragraph}>{paragraph}</p>)}
        </section>)}
        <section><h2>How do the main features compare?</h2><ComparisonTable columns={record.comparison.columns} rows={record.comparison.rows} /></section>
        <section id="faq"><h2>Frequently asked questions</h2>
          <div className="faq-list">{record.faqs.map(faq => <section key={faq.question}><h3>{faq.question}</h3><p>{faq.answer}</p></section>)}</div>
        </section>
        <SourcesList sources={getSources(record.sourceIds)} />
        <NextStep kind="question" slug={record.slug} />
      </article>
      <aside className="article-rail">
        <VideoPanel record={record} />
        {method && <div className="rail-card"><p className="eyebrow">How we know it</p><a href={`/methods/${method.id}/`}>{method.name}</a><small>{method.blurb}</small></div>}
        <div className="rail-card"><p className="eyebrow">Related zones</p>{record.relatedZones.map(slug => {
          const zone = getZoneBySlug(slug)
          return zone ? <a key={slug} href={`/zones/${slug}/`}>{zone.name}</a> : null
        })}</div>
        <div className="rail-card"><p className="eyebrow">Related creatures</p>{record.relatedCreatures.map(slug => {
          const creature = getCreatureBySlug(slug)
          return creature ? <a key={slug} href={canonicalPath(`/creatures/${slug}/`)}>{creature.name}</a> : null
        })}</div>
      </aside>
    </div>
  </main>
}
