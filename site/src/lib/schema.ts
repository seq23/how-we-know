import type { QuestionPageRecord } from './types'
import { getSources } from './sources-data'
import { absoluteUrl, site } from './site'
import { getMethod, getSubject } from './taxonomy'

export const organizationSchema = {
  '@context': 'https://schema.org',
  '@type': 'Organization',
  name: site.publisher,
  url: site.origin,
}

export const websiteSchema = {
  '@context': 'https://schema.org',
  '@type': 'WebSite',
  name: site.name,
  url: site.origin,
  description: site.description,
  inLanguage: 'en-US',
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
    image: absoluteUrl('/og-default.svg'),
    citation: getSources(record.sourceIds).map((source) => source.url),
    about: { '@type': 'Thing', name: getSubject(record.subject)?.name ?? record.subject },
    additionalProperty: {
      '@type': 'PropertyValue',
      name: 'Evidence method',
      value: getMethod(record.method)?.name ?? record.method,
      url: absoluteUrl(`/methods/${record.method}`),
    },
    author: { '@type': 'Organization', name: site.author },
    publisher: {
      '@type': 'Organization',
      name: site.publisher,
      url: site.origin,
    },
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
