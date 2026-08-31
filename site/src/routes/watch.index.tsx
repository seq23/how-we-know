import { createFileRoute } from '@tanstack/react-router'
import { hasPublishedVideo } from '~/lib/schema'
import { questions } from '~/lib/questions-data'
import { videoQueue } from '~/lib/video-data'
import { pageMeta } from '~/lib/seo'

export const Route = createFileRoute('/watch/')({
  head: () =>
    pageMeta(
      'Watch',
      'Published deep-sea videos and the transparent production slate for the companion faceless YouTube channel.',
      '/watch',
    ),
  component: WatchPage,
})

function WatchPage() {
  const published = questions.filter(hasPublishedVideo)
  const planned = videoQueue.filter((item) => !item.videoId)

  return (
    <main className="shell index-page">
      <header className="index-hero">
        <p className="eyebrow">Companion channel</p>
        <h1>One query. One article. One matching video.</h1>
        <p>
          Published episodes appear only after the public player, title, thumbnail, date, duration, transcript,
          and chapters are complete. The production slate below remains explicit about unfinished work.
        </p>
      </header>

      <section className="watch-section" aria-labelledby="published-videos">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Published</p>
            <h2 id="published-videos">Watchable episodes</h2>
          </div>
          <span>{published.length} live</span>
        </div>
        {published.length ? (
          <div className="watch-grid">
            {published.map((record) => (
              <article className="watch-card" id={record.slug} key={record.slug}>
                <div className="video-frame">
                  <iframe
                    src={`https://www.youtube-nocookie.com/embed/${record.video.videoId}`}
                    title={record.video.title || record.question}
                    loading="lazy"
                    allowFullScreen
                  />
                </div>
                <div>
                  <p className="eyebrow">Published {record.video.uploadDate}</p>
                  <h3>{record.video.title}</h3>
                  <p>{record.directAnswer}</p>
                  <a href={`/questions/${record.slug}`}>Read the canonical sourced article →</a>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <strong>No videos are public yet.</strong>
            <p>The Watch page is structurally ready, but it will not render fabricated players or video schema.</p>
          </div>
        )}
      </section>

      <section className="watch-section" aria-labelledby="production-slate">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Production queue</p>
            <h2 id="production-slate">Initial twenty-video release sequence</h2>
          </div>
          <span>{planned.length} awaiting production</span>
        </div>
        <div className="queue-table">
          {videoQueue.map((item) => (
            <div className="queue-row" key={item.sequence}>
              <span>{String(item.sequence).padStart(2, '0')}</span>
              <div>
                <strong>{item.query}</strong>
                <small>
                  {item.articlePath ? <a href={item.articlePath}>Canonical article</a> : 'Article admission required'}
                </small>
              </div>
              <em>{item.videoId ? 'published' : item.status}</em>
            </div>
          ))}
        </div>
      </section>
    </main>
  )
}
