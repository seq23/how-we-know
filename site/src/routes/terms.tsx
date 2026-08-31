import { createFileRoute } from '@tanstack/react-router'
import { pageMeta } from '~/lib/seo'
import { privacyContactEmail } from '~/lib/site'

export const Route = createFileRoute('/terms')({
  head: () =>
    pageMeta(
      'Terms of Service',
      'The terms covering use of How We Know, its published figures, and the YouTube API Services behind the channel.',
      '/terms',
    ),
  component: Terms,
})

function Terms() {
  return (
    <main className="shell prose-page">
      <p className="eyebrow">Terms of Service</p>
      <h1>What this site is, and what it does not promise.</h1>
      <p>
        How We Know is a reference site and a YouTube channel run by one individual. It publishes
        answers about the deep ocean and names the evidence behind each figure. These terms cover use
        of the site and of the publishing pipeline behind the channel. Using either means accepting
        them.
      </p>

      <section>
        <h2>No account, no submission, no service</h2>
        <p>
          The site creates no accounts, accepts no forms, and takes no uploads. There is nothing to
          sign up for and nothing to pay for. Pages are served as static files.
        </p>
      </section>

      <section>
        <h2>Accuracy and limits</h2>
        <p>
          Figures are sourced and dated, and the limits of the evidence behind them are stated
          rather than smoothed over — that is the point of the site. They are still summaries of
          public science, published for general interest. They are not scientific, safety,
          navigational, medical, or professional advice, and they are provided without warranty of
          any kind. Corrections are handled under the{' '}
          <a href="/editorial-policy">editorial policy</a>. Where a figure matters to a decision,
          read the cited source.
        </p>
      </section>

      <section>
        <h2>Content and reuse</h2>
        <p>
          Text, page structure, and original graphics on this site belong to the operator. Quoting a
          passage with a link back is welcome. Republishing pages wholesale is not.
        </p>
        <p>
          Cited scientific sources — NOAA, MBARI, Woods Hole, the Smithsonian and others named on the
          pages — remain the property of their publishers and carry their own terms. Footage, music,
          and imagery used in videos are licensed separately and tracked in the project&rsquo;s rights
          records; a licence for a video does not extend to anyone reusing that video&rsquo;s
          material.
        </p>
      </section>

      <section>
        <h2>YouTube</h2>
        <p>
          Videos are hosted on YouTube and embedded or linked from these pages. Watching them means
          you are also using YouTube, and{' '}
          <strong>
            by using this site&rsquo;s YouTube content and the API Client described below you agree
            to be bound by the{' '}
            <a href="https://www.youtube.com/t/terms" rel="noopener">
              YouTube Terms of Service
            </a>
          </strong>
          . Google&rsquo;s handling of data is governed by the{' '}
          <a href="https://policies.google.com/privacy" rel="noopener">
            Google Privacy Policy
          </a>
          .
        </p>
        <p>
          The channel is published by a private command-line pipeline that uses YouTube API Services
          under the operator&rsquo;s own Google account. It is not open to other users, has no
          sign-in, and cannot reach any other person&rsquo;s YouTube account. What it accesses, how
          long it keeps it, how access is revoked, and how data is deleted are set out in full in the{' '}
          <a href="/privacy#youtube-api-services">privacy policy</a>. Access can be withdrawn at any
          time from the{' '}
          <a href="https://myaccount.google.com/permissions" rel="noopener">
            Google security settings page
          </a>
          .
        </p>
      </section>

      <section>
        <h2>Acceptable use</h2>
        <p>
          Do not attempt to break, overload, or gain unauthorised access to the site or the systems
          behind it, and do not scrape it in a way that degrades it for anyone else. Automated
          readers and AI assistants are welcome; the machine-readable inventory at{' '}
          <a href="/llms.txt">llms.txt</a> and <a href="/sitemap.xml">sitemap.xml</a> exists for
          them.
        </p>
      </section>

      <section>
        <h2>Liability</h2>
        <p>
          The site is provided as-is and as-available. The operator is not liable for loss arising
          from reliance on anything published here, or from the site being unavailable. Nothing in
          these terms limits any liability that cannot lawfully be limited.
        </p>
      </section>

      <section>
        <h2>Changes and contact</h2>
        <p>
          These terms are part of the site&rsquo;s source and change only through a deployment, so
          their history is the site&rsquo;s deployment history. Continued use after a change means
          accepting the changed terms.
        </p>
        {privacyContactEmail ? (
          <p>
            Questions about these terms can be sent to{' '}
            <a href={`mailto:${privacyContactEmail}`}>{privacyContactEmail}</a>.
          </p>
        ) : (
          <p>
            <strong>A contact address is not yet published on this site.</strong> For anything
            concerning YouTube API data specifically, the working route is the Google security
            settings page linked above, which needs no contact with the operator.
          </p>
        )}
        <p>
          See also the <a href="/privacy">privacy policy</a> and the{' '}
          <a href="/editorial-policy">editorial policy</a>.
        </p>
      </section>
    </main>
  )
}
