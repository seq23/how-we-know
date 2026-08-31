import { createFileRoute } from '@tanstack/react-router'
import { pageMeta } from '~/lib/seo'
import { privacyContactEmail } from '~/lib/site'

export const Route = createFileRoute('/privacy')({
  head: () =>
    pageMeta(
      'Privacy',
      'Privacy information for How We Know: site analytics, and the YouTube API Services used to publish the channel.',
      '/privacy',
    ),
  component: Privacy,
})

function Privacy() {
  return (
    <main className="shell prose-page">
      <p className="eyebrow">Privacy</p>
      <h1>Analytics is optional and disabled without configuration.</h1>
      <p>
        The site creates no accounts and accepts no forms. When a deployment owner supplies a Google
        Analytics measurement ID, the browser can send page and traffic-source classification events
        to Google Analytics.
      </p>
      <p>
        The classifier uses the referring domain and optional UTM parameters to separate identifiable
        AI-assistant referrals, organic search, YouTube, other referrals, and direct or
        unidentifiable visits. Some assistants and browsers suppress referrer data, so unidentified
        direct traffic must never be reported as proven AI traffic.
      </p>
      <p>
        No analytics script is loaded when <code>VITE_GA_MEASUREMENT_ID</code> is empty. Deployment
        owners must review consent, disclosure, retention, and jurisdictional requirements before
        enabling analytics.
      </p>

      <section id="youtube-api-services">
        <h2>YouTube API Services</h2>
        <p>
          How We Know is operated by one individual, who also owns and publishes the{' '}
          <a href="https://youtube.com/@howweknowdeep" rel="noopener">
            @howweknowdeep
          </a>{' '}
          YouTube channel. Publishing to that channel is done by a private command-line pipeline run
          on the operator&rsquo;s own computer. <strong>That pipeline uses YouTube API Services.</strong>{' '}
          This website is where its policy is published; the website itself makes no API calls, and
          nothing on this website signs a visitor in or asks a visitor to authorise anything.
        </p>
        <p>
          By using the pipeline, and by extension by using YouTube content it publishes, users are
          agreeing to be bound by the{' '}
          <a href="https://www.youtube.com/t/terms" rel="noopener">
            YouTube Terms of Service
          </a>
          . Google&rsquo;s handling of any data it receives is governed by the{' '}
          <a href="https://policies.google.com/privacy" rel="noopener">
            Google Privacy Policy
          </a>
          .
        </p>

        <h3>Who authorises it, and what it can reach</h3>
        <p>
          Exactly one Google account authorises the pipeline: the operator&rsquo;s own account, the
          one that owns the channel. There is no sign-in for anyone else, no multi-user
          installation, and no path by which a visitor to this site or a viewer of the channel can
          grant it access to their account. It cannot read any other person&rsquo;s YouTube account,
          watch history, subscriptions, or personal information.
        </p>
        <p>The pipeline requests only these authorisation scopes:</p>
        <ul>
          <li>
            <code>youtube.upload</code> — to upload the channel&rsquo;s own videos and set their
            title, description, and privacy status.
          </li>
          <li>
            <code>youtube.readonly</code> — to read back the status of videos it has itself
            uploaded, so a rejected or claimed upload is noticed rather than assumed successful.
          </li>
        </ul>
        <p>
          It also reads the channel&rsquo;s own performance figures from the YouTube Analytics API,
          scoped to <code>channel==MINE</code>. Those reports are aggregate per-video numbers —
          views, estimated minutes watched, and average view percentage. They identify videos, not
          viewers, and contain no personal information about anyone who watches the channel.
        </p>

        <h3>What is stored, where, and for how long</h3>
        <ul>
          <li>
            <strong>OAuth tokens.</strong> The access and refresh tokens issued to the operator&rsquo;s
            own account are written to a single file on the operator&rsquo;s computer, with
            owner-only file permissions, in a directory excluded from version control. They are never
            sent to this website, never stored on this website&rsquo;s servers, and never shared with
            anyone.
          </li>
          <li>
            <strong>Video records.</strong> Video IDs, titles, descriptions, and publication status
            for videos the pipeline itself uploaded, kept so the same video is not published twice.
          </li>
          <li>
            <strong>Aggregate channel metrics.</strong> The per-video figures described above, kept
            in a local file to track how the channel is performing over time.
          </li>
        </ul>
        <p>
          No YouTube API data is retained for longer than 30 calendar days without being refreshed
          from the API. Data that is not refreshed within 30 days is deleted. Nothing obtained
          through YouTube API Services is sold, rented, or disclosed to any third party, and none of
          it is used to build a profile of any person.
        </p>

        <h3>Cookies and device storage</h3>
        <p>
          The pipeline is a command-line program with no browser interface. It sets no cookies and
          stores nothing on any visitor&rsquo;s device. Cookie behaviour on this website is covered
          by the analytics section above; cookie behaviour on youtube.com is governed by the Google
          Privacy Policy linked above.
        </p>

        <h3>Third-party content and advertising</h3>
        <p>
          The pipeline serves no advertising and embeds no third-party advertising or content
          network of its own. Advertising shown alongside videos on YouTube is served by YouTube, not
          by this operator.
        </p>
      </section>

      <section id="data-deletion">
        <h2>Data deletion</h2>
        <p>
          <strong>Revoking access.</strong> The authorising account can withdraw the pipeline&rsquo;s
          access at any time from the Google security settings page —{' '}
          <a href="https://myaccount.google.com/permissions" rel="noopener">
            https://myaccount.google.com/permissions
          </a>{' '}
          (also reachable at{' '}
          <a href="https://security.google.com/settings/security/permissions" rel="noopener">
            security.google.com/settings/security/permissions
          </a>
          ). Revoking access immediately stops the pipeline from reaching the YouTube API.
        </p>
        <p>
          <strong>What happens on revocation.</strong> When access is revoked, or when the
          pipeline&rsquo;s authorisation can no longer be verified, all data obtained from YouTube
          API Services is deleted from the operator&rsquo;s storage within 7 calendar days. That
          includes the stored tokens, the video records, and the aggregate metrics.
        </p>
        <p>
          <strong>Requesting deletion.</strong> A request to delete data held about you is actioned
          within 30 days of receipt. Because the pipeline only ever holds data belonging to the
          single authorising account and aggregate figures about the channel&rsquo;s own videos, a
          request from any other person will normally be answered by confirming that no data about
          them is held.
        </p>
        <p>
          <strong>Deleting a published video.</strong> Deleting a video on YouTube removes it from
          YouTube. Its record is dropped from the pipeline&rsquo;s local files at the next run, and
          any page on this site referring to it is removed at the next deployment.
        </p>
      </section>

      <section id="contact">
        <h2>Questions, complaints, and deletion requests</h2>
        {privacyContactEmail ? (
          <p>
            Privacy questions, complaints about these practices, and data-deletion requests can be
            sent to <a href={`mailto:${privacyContactEmail}`}>{privacyContactEmail}</a>. Requests are
            answered within 30 days.
          </p>
        ) : (
          <p>
            <strong>
              A contact address for privacy questions and deletion requests is not yet published on
              this page.
            </strong>{' '}
            Until it is, the working route for withdrawing access and triggering deletion is the
            Google security settings page linked under <a href="#data-deletion">Data deletion</a>{' '}
            above, which requires no contact with the operator and takes effect immediately.
          </p>
        )}
      </section>

      <section id="changes">
        <h2>Changes to this policy</h2>
        <p>
          This policy is part of the site&rsquo;s source and changes only through a deployment, so
          its history is the site&rsquo;s deployment history. A material change to how YouTube API
          data is handled will be reflected here at the same time as the change itself.
        </p>
        <p>
          See also the <a href="/terms">Terms of Service</a> and the{' '}
          <a href="/editorial-policy">editorial policy</a>.
        </p>
      </section>
    </main>
  )
}
