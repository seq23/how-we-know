import { referencePage } from '~/lib/reference-page'
import type { CreatureRecord, OceanZoneRecord } from '~/lib/types'
import { NextStep } from './PublisherLine'
export function ReferenceDetails({ record, kind }: { record: CreatureRecord | OceanZoneRecord; kind: 'creature' | 'zone' }) {
  const page = referencePage(record, kind)
  return <>
    <section><h2>How does the surrounding habitat explain these features?</h2>
      <p>Read these related answers for the mechanism behind the reference facts. Each answer distinguishes an observation from an explanation and links its own evidence.</p>
      {page.related.slice(0, 3).map(q=><section key={q.slug}><h3><a href={`/questions/${q.slug}/`}>{q.question}</a></h3><p>{q.directAnswer}</p><p>{q.sections[0].paragraphs[0]}</p></section>)}
    </section>
    <section id="faq"><h2>Frequently asked questions</h2>{page.faqs.map(f=><section key={f.question}><h3>{f.question}</h3><p>{f.answer}</p></section>)}</section>
    <NextStep kind={kind} slug={record.slug} />
  </>
}
