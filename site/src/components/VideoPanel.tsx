import type { QuestionPageRecord } from '~/lib/types'
import { hasPublishedVideo } from '~/lib/schema'

export function VideoPanel({ record }: { record: QuestionPageRecord }) {
  if (!hasPublishedVideo(record)) {
    return (
      <aside className="video-pending">
        <p className="eyebrow">Companion video</p>
        <h2>Video not published yet</h2>
        <p>
          This article is complete without a video. When the matching episode is public, the player,
          transcript, chapters, Watch listing, video sitemap entry, and VideoObject metadata activate from the
          same canonical record.
        </p>
        <a href="/watch">See the production slate</a>
      </aside>
    )
  }

  return (
    <section className="video-panel">
      <div className="video-frame">
        <iframe
          src={`https://www.youtube-nocookie.com/embed/${record.video.videoId}`}
          title={record.video.title || record.question}
          loading="lazy"
          allowFullScreen
        />
      </div>
      <h2>{record.video.title}</h2>
      <a href={`/watch#${record.slug}`}>Open in the Watch library</a>
      {record.video.chapters.length > 0 && (
        <details className="video-details">
          <summary>Video chapters</summary>
          <ol>
            {record.video.chapters.map((chapter) => (
              <li key={`${chapter.time}-${chapter.title}`}>
                <span>{chapter.time}</span> {chapter.title}
              </li>
            ))}
          </ol>
        </details>
      )}
      {record.video.transcript && (
        <details className="video-details">
          <summary>Transcript</summary>
          <p>{record.video.transcript}</p>
        </details>
      )}
    </section>
  )
}
