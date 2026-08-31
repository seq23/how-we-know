import { useEffect } from 'react'
import { classifyTraffic } from '~/lib/traffic-source'
import { webAnalyticsToken } from '~/lib/site'

declare global {
  interface Window {
    dataLayer?: unknown[]
    gtag?: (...args: unknown[]) => void
  }
}

const SESSION_KEY = 'how-we-know:traffic-source'

/**
 * Cloudflare Web Analytics. Cookieless and privacy-preserving, so it needs no
 * consent banner. The token lives in site-flags.json; empty token => no beacon.
 */
function CloudflareWebAnalytics() {
  const token = webAnalyticsToken.trim()
  if (!token) return null
  return (
    <script
      defer
      src="https://static.cloudflareinsights.com/beacon.min.js"
      data-cf-beacon={JSON.stringify({ token })}
    />
  )
}

export function Analytics() {
  const measurementId = import.meta.env.VITE_GA_MEASUREMENT_ID?.trim()

  useEffect(() => {
    const classification = classifyTraffic({
      referrer: document.referrer,
      currentHost: window.location.hostname,
      search: window.location.search,
    })
    window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(classification))

    if (!measurementId) return

    window.dataLayer = window.dataLayer || []
    window.gtag = window.gtag || ((...args: unknown[]) => window.dataLayer?.push(args))

    if (!document.querySelector(`script[data-ga-measurement-id="${measurementId}"]`)) {
      const script = document.createElement('script')
      script.async = true
      script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(measurementId)}`
      script.dataset.gaMeasurementId = measurementId
      document.head.appendChild(script)
    }

    window.gtag('js', new Date())
    window.gtag('config', measurementId, { anonymize_ip: true })
    window.gtag('event', 'traffic_source_classified', {
      traffic_surface: classification.category,
      traffic_source_detail: classification.source,
      source_identifiable: classification.identifiable,
      referrer_host: classification.referrerHost || '(not available)',
      utm_source: classification.utmSource || '(not set)',
      utm_medium: classification.utmMedium || '(not set)',
    })
  }, [measurementId])

  return <CloudflareWebAnalytics />
}
