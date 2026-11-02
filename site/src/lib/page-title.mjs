/** Keep the query first; use branding only when it fits the result. */
export function pageTitle(query, brand = 'How We Know') {
  const text = query.replace(/\s+/gu, ' ').trim()
  const suffix = ` | ${brand}`
  if (text.length + suffix.length <= 65) return text === brand ? text : text + suffix
  if (text.length <= 65) return text
  const prefix = text.slice(0, 64)
  const boundary = prefix.lastIndexOf(' ')
  return (boundary >= 30 ? prefix.slice(0, boundary) : prefix).trimEnd() + '…'
}
