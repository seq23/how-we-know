import rawRules from '../../content/traffic-sources.json'

type TrafficCategory = 'ai-assistant' | 'organic-search' | 'youtube' | 'referral' | 'direct'
type TrafficRule = {
  id: string
  category: Exclude<TrafficCategory, 'referral' | 'direct'>
  domains: string[]
  utmSources: string[]
}

const rules = rawRules as TrafficRule[]

export type TrafficClassification = {
  category: TrafficCategory
  source: string
  referrerHost: string | null
  utmSource: string | null
  utmMedium: string | null
  identifiable: boolean
}

function normalizeHost(value: string) {
  return value.toLowerCase().replace(/^www\./, '')
}

function hostMatches(host: string, domain: string) {
  const normalizedDomain = normalizeHost(domain)
  return host === normalizedDomain || host.endsWith(`.${normalizedDomain}`)
}

export function classifyTraffic(input: {
  referrer: string
  currentHost: string
  search: string
}): TrafficClassification {
  const params = new URLSearchParams(input.search)
  const utmSource = params.get('utm_source')?.trim().toLowerCase() || null
  const utmMedium = params.get('utm_medium')?.trim().toLowerCase() || null

  if (utmSource) {
    const rule = rules.find((item) => item.utmSources.some((source) => source === utmSource))
    if (rule) {
      return {
        category: rule.category,
        source: rule.id,
        referrerHost: null,
        utmSource,
        utmMedium,
        identifiable: true,
      }
    }
  }

  if (!input.referrer) {
    return {
      category: 'direct',
      source: 'direct',
      referrerHost: null,
      utmSource,
      utmMedium,
      identifiable: false,
    }
  }

  let referrerHost: string | null = null
  try {
    referrerHost = normalizeHost(new URL(input.referrer).hostname)
  } catch {
    return {
      category: 'referral',
      source: 'unparseable-referrer',
      referrerHost: null,
      utmSource,
      utmMedium,
      identifiable: false,
    }
  }

  const currentHost = normalizeHost(input.currentHost)
  if (referrerHost === currentHost || referrerHost.endsWith(`.${currentHost}`)) {
    return {
      category: 'direct',
      source: 'internal',
      referrerHost,
      utmSource,
      utmMedium,
      identifiable: true,
    }
  }

  const rule = rules.find((item) => item.domains.some((domain) => hostMatches(referrerHost!, domain)))
  if (rule) {
    return {
      category: rule.category,
      source: rule.id,
      referrerHost,
      utmSource,
      utmMedium,
      identifiable: true,
    }
  }

  return {
    category: 'referral',
    source: referrerHost,
    referrerHost,
    utmSource,
    utmMedium,
    identifiable: true,
  }
}
