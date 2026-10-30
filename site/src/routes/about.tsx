import { createFileRoute } from '@tanstack/react-router'
import { pageMeta } from '~/lib/seo'
import { entity, site } from '~/lib/site'

/**
 * Who publishes this, and how a claim gets onto the site.
 *
 * Until 2026-10-25 there was no /about page at all: the methodology and the
 * editorial policy existed, but nothing said who was speaking. An answer engine
 * weighs the publisher before it weighs the answer, and an unnamed publisher is
 * the last one it cites. This page is the entity: the name, the sources it reads,
 * the review it applies, and the limits it admits to — each with a link to the
 * page that governs it rather than a claim that governs nothing.
 */
export const Route = createFileRoute('/about')({
  head: () => pageMeta('About How We Know', site.description, '/about'),
  component: About,
})

function About() {
  return (
    <main className="shell prose-page">
      <p className="eyebrow">About</p>
      <h1>How we know what we know.</h1>
      <p>
        {site.name} is an evidence-first publication about the deep ocean. Each page answers one
        real question and then does the part most writing about the deep sea skips: it names the
        instrument, the proxy or the single observation the answer rests on, and says where the
        evidence stops. Every published answer is paired with a video that makes the same claim in
        the same words, so the two surfaces cannot drift apart.
      </p>
      <section>
        <h2>Who publishes it</h2>
        <p>
          {site.name} is the publisher of both this site and the{' '}
          <a href={site.youtubeUrl} rel="noopener">
            {site.youtubeHandle}
          </a>{' '}
          video channel. The two carry one name, one editorial standard and one correction process.
          It is made by{' '}
          <a href={entity.parentOrganization.url} rel="noopener">
            {entity.parentOrganization.name}
          </a>
          , the independent studio behind it. Nothing here is sponsored, and nothing on the site is
          for sale: it is free to read and free to quote with a link back.
        </p>
      </section>
      <section>
        <h2>Who researches the videos</h2>
        <p>
          The {entity.parentOrganization.name} editorial team. Questions, sources and scripts are
          researched and drafted with AI assistance from named public research, then checked
          against those sources under <a href="/methodology">the written methodology</a> before
          anything is published: a figure that cannot be traced to a named public source does not
          go on screen or on the page. The narration is a synthetic voice, and any AI-generated
          image in a video is labelled as one on screen. No page claims review by an outside
          scientist; the authority behind each answer is the source it cites, and every page lists
          those sources so you can check them yourself.
        </p>
      </section>
      <section>
        <h2>Where the evidence comes from</h2>
        <p>
          Figures are traced to named public research — NOAA, MBARI, Woods Hole Oceanographic
          Institution, the Smithsonian and the published literature those bodies cite. A source is
          recorded with the date it was checked, and every page lists the sources behind it rather
          than gesturing at &ldquo;studies&rdquo;. Where a number is contested, the page gives the
          range and says who measured which end of it.
        </p>
      </section>
      <section>
        <h2>How an answer is checked</h2>
        <p>
          Questions are admitted, sourced and reviewed under a written process, not an editor&rsquo;s
          judgement on the day. <a href="/methodology">The methodology</a> sets out how a question
          is admitted, how sources are selected and how uncertainty is handled.{' '}
          <a href="/editorial-policy">The editorial policy</a> sets out the review and correction
          rules: a corrected claim is changed in the canonical record, the article, the script, the
          transcript, the video description and the structured data together, because a correction
          that reaches only one surface has not happened.
        </p>
      </section>
      <section>
        <h2>What the site will not do</h2>
        <p>
          It will not convert an unknown cause into a confident one, and it will not turn a single
          viral sighting into a trend. Unusual claims stay labelled as single observations until
          repeated evidence exists — which is also why answers are grouped by{' '}
          <a href="/methods">how they are known</a> rather than only by subject. A figure measured
          by an instrument and a figure inferred from a proxy are different kinds of fact, and the
          site says which kind it is handing you.
        </p>
      </section>
      <section>
        <h2>Corrections and questions</h2>
        <p>
          If a figure here is wrong, the page that carries it is the thing that changes, along with
          every other surface that repeats it. Review dates are carried on the pages themselves, and
          a page is re-reviewed when a material fact behind it moves. Start with{' '}
          <a href="/questions">the questions</a> or{' '}
          <a href="/explore">the depth explorer</a>, and the{' '}
          <a href="/llms.txt">llms.txt</a> file lists every canonical answer in one machine-readable
          place.
        </p>
      </section>
    </main>
  )
}
