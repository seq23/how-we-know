import { createFileRoute } from '@tanstack/react-router'
import { questions } from '~/lib/questions-data'
import { pageMeta } from '~/lib/seo'
export const Route=createFileRoute('/questions/')({head:()=>pageMeta('Questions','Direct, sourced answers to real questions about deep-sea animals, pressure, color, light and ocean zones.','/questions'),component:QuestionsIndex})
function QuestionsIndex(){return <main className="shell index-page"><header className="index-hero"><p className="eyebrow">Question library</p><h1>Start with the exact question.</h1><p>Every page opens with a liftable direct answer, then shows the evidence, limits, comparisons, related zones and companion-video status.</p></header><div className="card-grid">{questions.map((item)=><a className="question-card" key={item.slug} href={`/questions/${item.slug}`}><span>Reviewed {item.reviewedAt}</span><h2>{item.question}</h2><p>{item.directAnswer}</p></a>)}</div></main>}
