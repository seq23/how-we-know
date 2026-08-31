export function KeyStat({
  value,
  label,
  sourceName,
  sourceUrl,
  sourceCheckedAt,
}: {
  value: string
  label: string
  sourceName: string
  sourceUrl: string
  sourceCheckedAt: string
}) {
  return (
    <aside className="key-stat">
      <span>{value}</span>
      <p>{label}</p>
      <a href={sourceUrl} target="_blank" rel="noreferrer">
        Source: {sourceName} · checked {sourceCheckedAt}
      </a>
    </aside>
  )
}
