import { createFileRoute } from '@tanstack/react-router'
import { DepthExplorer } from '~/components/DepthExplorer'
import { pageMeta } from '~/lib/seo'

export const Route = createFileRoute('/explore')({
  head: () =>
    pageMeta(
      'Explore ocean depth',
      'Scroll from the surface to Challenger Deep as ocean zones, pressure, temperature, light, and deep-sea creatures change with depth.',
      '/explore',
    ),
  component: ExplorePage,
})

function ExplorePage() {
  return (
    <main>
      <header className="explore-hero shell">
        <p className="eyebrow">Surface to trench</p>
        <h1>The ocean is not one habitat.</h1>
        <p className="dek">
          Descend through five publishing zones, see representative animals at their approximate depth ranges,
          and end at the deepest known seafloor in Challenger Deep.
        </p>
        <p className="explorer-caveat">
          Zone boundaries and environmental readings are simplified reference conventions. Follow the linked
          zone, creature, and question pages for sources and limits.
        </p>
      </header>
      <DepthExplorer />
      <section className="shell explorer-afterword">
        <p className="eyebrow">Canonical answer</p>
        <h2>What is at the bottom?</h2>
        <p>
          Challenger Deep is the deepest known part of the global ocean. Its modern published depth is about
          10,935 meters, with small differences among surveys because methods and uncertainty differ.
        </p>
        <a className="button" href="/questions/what-is-the-deepest-part-of-the-ocean">
          Read the sourced answer
        </a>
      </section>
    </main>
  )
}
