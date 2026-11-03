import { referencePage } from '~/lib/reference-page'
import type { CreatureRecord, OceanZoneRecord } from '~/lib/types'
import { NextStep } from './PublisherLine'
export function ReferenceDetails({ record, kind }: { record: CreatureRecord | OceanZoneRecord; kind: 'creature' | 'zone' }) {
  const page = referencePage(record, kind)
  return <>
    {/*
      Related answers are links, not copies. Until 2026-11-03 this section reprinted each
      related question's direct answer AND its first body paragraph, so every reference page
      carried several paragraphs lifted from other pages: /zones/hadal/ and
      /creatures/hadal-snailfish/ measured 0.61 on the audit's own near-duplicate test
      (fails above 0.50) because they list the same related questions. A link carries the
      same reader somewhere without publishing the other page's words twice.
    */}
    <section><h2>What explains the {record.name.toLowerCase()} record?</h2>
      <p>These answers carry the mechanism behind the {record.name.toLowerCase()} facts above, each with its own sources and its own account of where observation ends and inference begins.</p>
      <ul>{page.related.slice(0, 3).map(q=><li key={q.slug}><a href={`/questions/${q.slug}/`}>{q.question}</a></li>)}</ul>
    </section>
    <section id="faq"><h2>Frequently asked questions</h2>{page.faqs.map(f=><section key={f.question}><h3>{f.question}</h3><p>{f.answer}</p></section>)}</section>
    <NextStep kind={kind} slug={record.slug} />
  </>
}
