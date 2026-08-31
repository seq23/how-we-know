import { site } from '~/lib/site'

/**
 * The sounding line: a sea-level rule, a descent line with depth ticks, and an
 * amber weight at the bottom. Same mark as the channel avatar, banner and
 * watermark. It stays fixed across every subject.
 */
export function SoundingLineMark({ size = 22 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      role="img"
      aria-hidden="true"
      focusable="false"
    >
      <rect x="6" y="9" width="52" height="5" rx="1" fill="var(--color-glow)" />
      <rect x="29" y="9" width="6" height="38" fill="var(--color-water-300)" />
      <rect x="17" y="24" width="30" height="5" rx="1" fill="var(--color-water-300)" />
      <rect x="19" y="33" width="26" height="5" rx="1" fill="var(--color-water-300)" />
      <rect x="22" y="42" width="20" height="5" rx="1" fill="var(--color-water-300)" />
      <circle cx="32" cy="53" r="9" fill="var(--color-accent)" />
    </svg>
  )
}

export function SiteHeader() {
  return (
    <header className="site-header">
      <div className="shell header-inner">
        <a className="brand" href="/">
          <span className="brand-mark" aria-hidden="true">
            <SoundingLineMark />
          </span>
          <span>{site.name}</span>
        </a>
        <nav className="primary-nav" aria-label="Primary navigation">
          <a href="/questions">Questions</a>
          <a href="/methods">How we know it</a>
          <a href="/explore">Explore</a>
          <a href="/creatures">Creatures</a>
          <a href="/zones">Zones</a>
          <a href="/watch">Watch</a>
        </nav>
      </div>
    </header>
  )
}
