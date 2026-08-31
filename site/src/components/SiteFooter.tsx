import { site } from '~/lib/site'

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="shell footer-grid">
        <div>
          <strong>{site.name}</strong>
          <p>
            Answers built from NOAA, MBARI, Woods Hole, Smithsonian and other named public sources.
            Every figure names the evidence behind it, and the limits of that evidence are stated
            rather than smoothed over.
          </p>
          <a href={site.youtubeUrl} rel="noopener">
            YouTube · {site.youtubeHandle}
          </a>
        </div>
        <div>
          <strong>Editorial</strong>
          <a href="/methods">How we know it</a>
          <a href="/methodology">Methodology</a>
          <a href="/editorial-policy">Editorial policy</a>
          <a href="/privacy">Privacy policy</a>
          <a href="/terms">Terms of Service</a>
        </div>
        <div>
          <strong>Machine-readable</strong>
          <a href="/sitemap.xml">Sitemap</a>
          <a href="/llms.txt">llms.txt</a>
          <a href="/robots.txt">Robots</a>
        </div>
      </div>
    </footer>
  )
}
