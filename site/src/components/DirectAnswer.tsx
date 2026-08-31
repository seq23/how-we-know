import type { ReactNode } from 'react'

export function DirectAnswer({ children }: { children: ReactNode }) {
  return (
    <section className="direct-answer" aria-labelledby="direct-answer-title">
      <p className="answer-label" id="direct-answer-title">
        Direct answer
      </p>
      <p>{children}</p>
    </section>
  )
}
