import { createFileRoute } from '@tanstack/react-router'
import { creatures } from '~/lib/creatures-data'
import { pageMeta } from '~/lib/seo'
export const Route=createFileRoute('/creatures/')({head:()=>pageMeta('Deep-sea creatures','An evidence-backed starter library of iconic deep-sea animals and the adaptations behind their appearance.','/creatures'),component:CreaturesIndex})
function CreaturesIndex(){return <main className="shell index-page"><header className="index-hero"><p className="eyebrow">Creature library</p><h1>Look past the close-up.</h1><p>Each record connects anatomy to the actual environmental problem it helps solve.</p></header><div className="card-grid">{creatures.map((item)=><a className="creature-card" key={item.slug} href={`/creatures/${item.slug}`}><span>{item.scientificName}</span><h2>{item.name}</h2><p>{item.summary}</p></a>)}</div></main>}
