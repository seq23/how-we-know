import { site } from '~/lib/site'
export function PublisherLine({ publishedAt, updatedAt }: { publishedAt: string; updatedAt: string }) {
  return <p className="reviewed">By <a href="/about/" rel="author">{site.author}</a> · Publisher: {site.publisher} · Published <time dateTime={publishedAt}>{publishedAt}</time> · Updated <time dateTime={updatedAt}>{updatedAt}</time></p>
}
export function NextStep({ kind, slug }: { kind: string; slug: string }) {
  return <aside className="rail-card"><h2>What can you explore next?</h2><p>Compare the evidence across ocean depths, then follow the sources behind the answer.</p><a href={`/explore/?kind=${encodeURIComponent(kind)}&slug=${encodeURIComponent(slug)}/`}>Explore the ocean by depth</a></aside>
}
