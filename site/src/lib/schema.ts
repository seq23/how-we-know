import type { QuestionPageRecord } from './types'
import { getSources } from './sources-data'
import { absoluteUrl, entity, site } from './site'
import { getMethod, getSubject } from './taxonomy'

export const organizationId = `${site.origin}/#organization`
export const websiteId = `${site.origin}/#website`

/**
 * The publisher, with everything an answer engine needs to resolve it to one entity.
 *
 * Until 2026-10-25 this node carried only a name and a url. A logo and at least
 * one sameAs are what let an engine tie the pages, the YouTube channel and the
 * name together as one publisher rather than three unrelated strings, and the
 * audit reads all four fields on every page. Because the same object is reused as
 * the author and publisher of every Article, every Organization node on the site
 * is this one — a page with a name-only publisher node was the same gap again.
 */
export const organizationSchema = {
  '@context': 'https://schema.org',
  '@type': 'Organization',
  '@id': organizationId,
  name: site.publisher,
  url: site.origin,
  description: site.description,
  logo: {
    '@type': 'ImageObject',
    url: absoluteUrl('/logo.png'),
    width: 512,
    height: 512,
    caption: site.name,
  },
  sameAs: entity.sameAs,
  // A reference by @id, not a second Organization node: Spry Labs' full node
  // lives on its own entity home, and validate-built-html requires every
  // Organization node emitted HERE to carry its own logo and sameAs.
  parentOrganization: {
    '@id': entity.parentOrganization['@id'],
    name: entity.parentOrganization.name,
    url: entity.parentOrganization.url,
  },
}

/** The publisher as it appears nested inside another node: the same entity, by id. */
const publisherNode = { ...organizationSchema, '@context': undefined }

export const websiteSchema = {
  '@context': 'https://schema.org',
  '@type': 'WebSite',
  '@id': websiteId,
  name: site.name,
  url: site.origin,
  description: site.description,
  inLanguage: 'en-US',
  publisher: publisherNode,
}

/**
 * The page itself, on every page.
 *
 * The audit's rule is a WebPage (or subtype) on every sampled page and a WebSite
 * on the homepage; on 2026-10-25 the site had the WebSite and no WebPage anywhere,
 * so no page declared which site it belonged to. No date goes on this node: a
 * date in schema that is not also visible on the page is its own defect.
 */
export function webPageSchema(page: {
  url: string
  name: string
  description: string
  type: 'website' | 'article'
}) {
  return {
    '@context': 'https://schema.org',
    '@type': page.type === 'article' ? 'ItemPage' : 'WebPage',
    '@id': `${page.url}#webpage`,
    url: page.url,
    name: page.name,
    description: page.description,
    isPartOf: { '@id': websiteId },
    publisher: { '@id': organizationId },
    primaryImageOfPage: { '@type': 'ImageObject', url: absoluteUrl('/og-default.png'), width: 1200, height: 630 },
    inLanguage: 'en-US',
  }
}

/**
 * What the site offers, and what it costs.
 *
 * Everything here is free to read and free to cite, and that is a fact about the
 * offer rather than a missing price: a priced Offer is how an answer engine reads
 * what a site provides, and leaving it out left the question unanswered. The price
 * is 0 and the homepage says so in words, so the schema and the page agree.
 */
export const serviceSchema = {
  '@context': 'https://schema.org',
  '@type': 'Service',
  '@id': `${site.origin}/#service`,
  name: 'Evidence-backed deep-ocean answers',
  description:
    'Sourced answers to questions about the deep ocean, each naming the instrument, proxy or single observation behind it, with a paired video for every published answer.',
  serviceType: 'Reference publication',
  provider: { '@id': organizationId },
  areaServed: 'Worldwide',
  audience: { '@type': 'Audience', audienceType: 'Readers, educators and answer engines' },
  offers: {
    '@type': 'Offer',
    price: '0',
    priceCurrency: 'USD',
    availability: 'https://schema.org/InStock',
    category: 'Free',
    url: site.origin,
  },
}

export function breadcrumbSchema(items: { name: string; path: string }[]) {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: items.map((item, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: item.name,
      item: absoluteUrl(item.path),
    })),
  }
}

export function articleSchema(record: QuestionPageRecord) {
  return {
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline: record.question,
    description: record.description,
    datePublished: record.publishedAt,
    dateModified: record.reviewedAt,
    inLanguage: 'en-US',
    isAccessibleForFree: true,
    mainEntityOfPage: absoluteUrl(`/questions/${record.slug}`),
    image: absoluteUrl('/og-default.png'),
    citation: getSources(record.sourceIds).map((source) => source.url),
    about: { '@type': 'Thing', name: getSubject(record.subject)?.name ?? record.subject },
    additionalProperty: {
      '@type': 'PropertyValue',
      name: 'Evidence method',
      value: getMethod(record.method)?.name ?? record.method,
      url: absoluteUrl(`/methods/${record.method}`),
    },
    author: publisherNode,
    publisher: publisherNode,
  }
}

export function faqSchema(record: QuestionPageRecord) {
  return {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: record.faqs.map((faq) => ({
      '@type': 'Question',
      name: faq.question,
      acceptedAnswer: { '@type': 'Answer', text: faq.answer },
    })),
  }
}

export function hasPublishedVideo(record: QuestionPageRecord) {
  const video = record.video
  return (
    video.status === 'published' &&
    Boolean(
      video.videoId?.trim() &&
        video.title &&
        video.descriptionFirstLine &&
        video.thumbnailUrl &&
        video.uploadDate &&
        video.duration &&
        video.transcript,
    )
  )
}

export function videoSchema(record: QuestionPageRecord) {
  if (!hasPublishedVideo(record)) return null

  const video = record.video
  return {
    '@context': 'https://schema.org',
    '@type': 'VideoObject',
    name: video.title,
    description: video.descriptionFirstLine,
    thumbnailUrl: [video.thumbnailUrl],
    uploadDate: video.uploadDate,
    duration: video.duration,
    embedUrl: `https://www.youtube.com/embed/${video.videoId}`,
    contentUrl: `https://www.youtube.com/watch?v=${video.videoId}`,
    transcript: video.transcript,
  }
}

export function jsonLdScript(value: unknown) {
  return { type: 'application/ld+json', children: JSON.stringify(value) }
}
