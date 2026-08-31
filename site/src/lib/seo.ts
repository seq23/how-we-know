import { absoluteUrl, site } from './site'
export function pageMeta(title: string, description: string, path: string, type: 'website' | 'article' = 'website') {
  const fullTitle = title === site.name ? title : `${title} | ${site.name}`
  const image = absoluteUrl('/og-default.svg')
  return {
    meta: [
      { title: fullTitle },
      { name: 'description', content: description },
      { property: 'og:title', content: fullTitle },
      { property: 'og:description', content: description },
      { property: 'og:type', content: type },
      { property: 'og:url', content: absoluteUrl(path) },
      { property: 'og:image', content: image },
      { name: 'twitter:card', content: 'summary_large_image' },
      { name: 'twitter:title', content: fullTitle },
      { name: 'twitter:description', content: description },
      { name: 'twitter:image', content: image },
    ],
    links: [{ rel: 'canonical', href: absoluteUrl(path) }],
  }
}
