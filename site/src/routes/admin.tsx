import { createFileRoute } from '@tanstack/react-router'
import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import {
  adminSnapshot,
  defaultGithubRepository,
  githubHref,
  isGithubRepository,
  normalizeGithubRepository,
} from '~/lib/admin'
import { absoluteUrl, site } from '~/lib/site'

export const Route = createFileRoute('/admin')({
  head: () => ({
    meta: [
      { title: `Production Admin | ${site.name}` },
      {
        name: 'description',
        content: 'Credentialless production guide for the twenty-video How We Know launch.',
      },
      { name: 'robots', content: 'noindex, nofollow, noarchive' },
      { property: 'og:title', content: `Production Admin | ${site.name}` },
      { property: 'og:url', content: absoluteUrl('/admin') },
    ],
  }),
  component: AdminPage,
})

const workflowFiles = {
  audition: 'voice-audition.yml',
  approve: 'approve-human-pass.yml',
  render: 'render-launch-batch.yml',
} as const

function AdminPage() {
  const [repositoryInput, setRepositoryInput] = useState(defaultGithubRepository)
  const [savedRepository, setSavedRepository] = useState(defaultGithubRepository)

  useEffect(() => {
    const stored = window.localStorage.getItem('deep-sea-github-repository') || ''
    if (stored) {
      setRepositoryInput(stored)
      setSavedRepository(stored)
    }
  }, [])

  const repository = normalizeGithubRepository(savedRepository)
  const repositoryReady = isGithubRepository(repository)

  function saveRepository() {
    const normalized = normalizeGithubRepository(repositoryInput)
    if (!isGithubRepository(normalized)) return
    window.localStorage.setItem('deep-sea-github-repository', normalized)
    setRepositoryInput(normalized)
    setSavedRepository(normalized)
  }

  const links = useMemo(
    () => ({
      repo: githubHref(repository, 'repo'),
      actions: githubHref(repository, 'actions'),
      audition: githubHref(repository, 'workflow', workflowFiles.audition),
      approve: githubHref(repository, 'workflow', workflowFiles.approve),
      render: githubHref(repository, 'workflow', workflowFiles.render),
      narratorSelection: githubHref(repository, 'edit', 'production/narrator-selection.json'),
      narratorScorecard: githubHref(repository, 'edit', 'production/narrator-scorecard.csv'),
      scripts: githubHref(repository, 'tree', 'production/scripts/final'),
      plaintext: githubHref(repository, 'tree', 'production/scripts/plaintext'),
      humanPass: githubHref(repository, 'tree', 'production/human-pass'),
      approvalLedger: githubHref(repository, 'blob', 'production/human-pass/approval-ledger.json'),
      metadata: githubHref(repository, 'tree', 'production/metadata'),
      outputs: githubHref(repository, 'tree', 'production/outputs'),
      receipts: githubHref(repository, 'tree', 'production/provider-receipts/youtube'),
      activationRunbook: githubHref(repository, 'blob', 'docs/runbooks/TWENTY_VIDEO_ACTIVATION.md'),
      youtubeRunbook: githubHref(repository, 'blob', 'docs/runbooks/youtube-publishing.md'),
      uploadScript: githubHref(repository, 'blob', 'production/automation/upload_batch.py'),
      syncScript: githubHref(repository, 'blob', 'production/automation/sync_site_from_receipts.py'),
    }),
    [repository],
  )

  return (
    <main className="shell admin-page">
      <header className="admin-hero">
        <p className="eyebrow">Owner operations guide</p>
        <h1>Twenty-video launch control map</h1>
        <p>
          This page stores no credentials and performs no provider mutation. It opens the exact GitHub files and
          workflows that do the work, then explains what successful completion looks like.
        </p>
      </header>

      <section className="admin-repo-panel" id="repository-link" aria-labelledby="repository-link-title">
        <div>
          <p className="eyebrow">One-time browser setting</p>
          <h2 id="repository-link-title">Connect the links to your existing GitHub repository</h2>
          <p>
            Paste <strong>owner/repository</strong>. It is saved only in this browser&apos;s local storage. It is not a
            password, token, or GitHub connection.
          </p>
        </div>
        <div className="admin-repo-form">
          <label htmlFor="github-repository">GitHub repository</label>
          <div>
            <input
              id="github-repository"
              value={repositoryInput}
              onChange={(event) => setRepositoryInput(event.target.value)}
              placeholder="owner/how-we-know"
              spellCheck={false}
              autoCapitalize="none"
            />
            <button type="button" onClick={saveRepository} disabled={!isGithubRepository(repositoryInput)}>
              Save links
            </button>
          </div>
          <small>
            {repositoryReady
              ? `Links currently target github.com/${repository}.`
              : 'Enter a valid owner/repository value to activate GitHub links.'}
          </small>
        </div>
      </section>

      <section className="admin-status-section" aria-labelledby="snapshot-status">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Deployed snapshot</p>
            <h2 id="snapshot-status">Readiness status</h2>
          </div>
          <span>{adminSnapshot.releaseGate.label}</span>
        </div>
        <p className="admin-status-note">
          These counts come from the files included in this deployed snapshot. GitHub may be newer until the site is
          rebuilt and deployed again.
        </p>
        <div className="admin-metrics">
          <StatusMetric label="Narrator" value={adminSnapshot.narrator.label} state={adminSnapshot.narrator.state} />
          <StatusMetric
            label="Human approvals"
            value={`${adminSnapshot.humanPass.approved}/${adminSnapshot.humanPass.total}`}
            state={adminSnapshot.humanPass.approved === adminSnapshot.humanPass.total ? 'ready' : 'pending'}
          />
          <StatusMetric
            label="Narration WAVs"
            value={`${adminSnapshot.production.narrationWavs}/${adminSnapshot.humanPass.total}`}
            state={adminSnapshot.production.narrationWavs === adminSnapshot.humanPass.total ? 'ready' : 'pending'}
          />
          <StatusMetric
            label="MP4 masters"
            value={`${adminSnapshot.production.renderedMp4s}/${adminSnapshot.humanPass.total}`}
            state={adminSnapshot.production.renderedMp4s === adminSnapshot.humanPass.total ? 'ready' : 'pending'}
          />
          <StatusMetric
            label="YouTube IDs"
            value={`${adminSnapshot.youtube.liveIds}/${adminSnapshot.humanPass.total}`}
            state={adminSnapshot.youtube.liveIds === adminSnapshot.humanPass.total ? 'ready' : 'pending'}
          />
          <StatusMetric
            label="Site activations"
            value={`${adminSnapshot.site.publishedVideos}/${adminSnapshot.humanPass.total}`}
            state={adminSnapshot.site.publishedVideos === adminSnapshot.humanPass.total ? 'ready' : 'pending'}
          />
        </div>
      </section>

      <section className="admin-workflow" aria-labelledby="launch-sequence">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Do these in order</p>
            <h2 id="launch-sequence">Launch sequence</h2>
          </div>
          <LinkOrDisabled href={links.activationRunbook}>Full activation runbook</LinkOrDisabled>
        </div>

        <AdminStep number="1" title="Generate the Kokoro audition" changes="Creates downloadable WAV artifacts only">
          <p>Run the voice-audition workflow with the default voice and three speeds. Download and listen to all files.</p>
          <LinkOrDisabled href={links.audition}>Open voice-audition workflow</LinkOrDisabled>
        </AdminStep>

        <AdminStep number="2" title="Record the human narrator decision" changes="Commits only after you edit the files">
          <p>Choose the voice and speed after listening on headphones, laptop speakers, and a phone.</p>
          <div className="admin-link-row">
            <LinkOrDisabled href={links.narratorSelection}>Edit narrator selection</LinkOrDisabled>
            <LinkOrDisabled href={links.narratorScorecard}>Edit narrator scorecard</LinkOrDisabled>
          </div>
        </AdminStep>

        <AdminStep number="3" title="Review and approve all twenty scripts" changes="Approval workflow commits the script hash">
          <p>
            Edit the final Markdown, plaintext narration, and matching human-pass checklist. Then run the approval
            workflow once per video. It refuses incomplete checklists, placeholders, or missing truthful [HUMAN] text.
          </p>
          <div className="admin-link-row">
            <LinkOrDisabled href={links.scripts}>Open final scripts</LinkOrDisabled>
            <LinkOrDisabled href={links.plaintext}>Open narration text</LinkOrDisabled>
            <LinkOrDisabled href={links.humanPass}>Open human-pass files</LinkOrDisabled>
            <LinkOrDisabled href={links.approve}>Run approval workflow</LinkOrDisabled>
            <LinkOrDisabled href={links.approvalLedger}>View approval ledger</LinkOrDisabled>
          </div>
          <ScriptApprovalTable repository={repository} repositoryReady={repositoryReady} approveHref={links.approve} />
        </AdminStep>

        <AdminStep number="4" title="Render twenty narration WAVs and MP4 masters" changes="Creates downloadable workflow artifacts">
          <p>
            Run only after the approval ledger reaches 20/20. Enter the approved Kokoro voice and speed. Download both
            the narration and MP4 artifacts from the completed workflow run.
          </p>
          <div className="admin-link-row">
            <LinkOrDisabled href={links.render}>Open twenty-video render workflow</LinkOrDisabled>
            <LinkOrDisabled href={links.actions}>View all workflow runs</LinkOrDisabled>
          </div>
        </AdminStep>

        <AdminStep number="5" title="Review the masters and prepare YouTube" changes="Human review plus local OAuth setup">
          <p>
            Watch each opening, chapter transition, middle section, and ending. Then follow the YouTube runbook to keep
            OAuth files outside the repository.
          </p>
          <div className="admin-link-row">
            <LinkOrDisabled href={links.outputs}>View output folder</LinkOrDisabled>
            <LinkOrDisabled href={links.metadata}>Review upload metadata</LinkOrDisabled>
            <LinkOrDisabled href={links.youtubeRunbook}>Open YouTube runbook</LinkOrDisabled>
          </div>
        </AdminStep>

        <AdminStep number="6" title="Dry-run, upload, and schedule" changes="Dry run is local only; publish mode mutates YouTube">
          <p>First produce receipts with no IDs. Inspect all dates and titles. Only then rerun with the publish flag.</p>
          <CommandBlock>{`python production/automation/upload_batch.py \\\n  --start-date YYYY-MM-DD \\\n  --timezone America/Chicago \\\n  --limit 20`}</CommandBlock>
          <CommandBlock>{`YOUTUBE_TOKEN_JSON=~/secure/deep-sea/youtube-token.json \\\npython production/automation/upload_batch.py \\\n  --start-date YYYY-MM-DD \\\n  --timezone America/Chicago \\\n  --limit 20 \\\n  --publish`}</CommandBlock>
          <div className="admin-link-row">
            <LinkOrDisabled href={links.uploadScript}>Inspect upload script</LinkOrDisabled>
            <LinkOrDisabled href={links.receipts}>View YouTube receipts</LinkOrDisabled>
          </div>
        </AdminStep>

        <AdminStep number="7" title="Activate public videos on the site" changes="Writes real provider data into canonical records">
          <p>Run only after each scheduled video is visibly public and playable.</p>
          <CommandBlock>{`python production/automation/sync_site_from_receipts.py --confirm-public\nnpm run generate\nnpm run validate\nnpm test\nnpm run build`}</CommandBlock>
          <LinkOrDisabled href={links.syncScript}>Inspect site-sync script</LinkOrDisabled>
        </AdminStep>
      </section>

      <section className="admin-boundary" aria-labelledby="admin-boundary-title">
        <p className="eyebrow">Truth boundary</p>
        <h2 id="admin-boundary-title">What this page does not do</h2>
        <ul>
          <li>It does not store GitHub, Google, YouTube, or Cloudflare credentials.</li>
          <li>It does not know whether a live workflow is running or whether YouTube accepted an upload.</li>
          <li>It does not approve editorial work, create provider receipts, or mark a video public.</li>
          <li>GitHub enforces login and repository permissions after you follow a link.</li>
        </ul>
      </section>
    </main>
  )
}

function StatusMetric({ label, value, state }: { label: string; value: string; state: string }) {
  return (
    <div className={`admin-metric admin-metric-${state}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function AdminStep({
  number,
  title,
  changes,
  children,
}: {
  number: string
  title: string
  changes: string
  children: ReactNode
}) {
  return (
    <article className="admin-step">
      <div className="admin-step-number">{number}</div>
      <div className="admin-step-content">
        <div className="admin-step-heading">
          <h3>{title}</h3>
          <span>{changes}</span>
        </div>
        {children}
      </div>
    </article>
  )
}

function LinkOrDisabled({ href, children }: { href: string; children: ReactNode }) {
  if (!href) return <span className="admin-link-disabled">Save the repository address to activate this link</span>
  return (
    <a className="admin-action-link" href={href} target="_blank" rel="noreferrer">
      {children} ↗
    </a>
  )
}

function CommandBlock({ children }: { children: string }) {
  return (
    <pre className="admin-command">
      <code>{children}</code>
    </pre>
  )
}

function ScriptApprovalTable({
  repository,
  repositoryReady,
  approveHref,
}: {
  repository: string
  repositoryReady: boolean
  approveHref: string
}) {
  return (
    <div className="admin-script-table" aria-label="Twenty script approval records">
      {adminSnapshot.humanPass.items.map((item) => {
        const scriptHref = repositoryReady ? githubHref(repository, 'edit', item.finalScriptPath) : ''
        const narrationHref = repositoryReady ? githubHref(repository, 'edit', item.plaintextPath) : ''
        const checklistHref = repositoryReady ? githubHref(repository, 'edit', item.humanPassPath) : ''
        return (
          <div className="admin-script-row" key={item.sequence}>
            <span>{String(item.sequence).padStart(2, '0')}</span>
            <div>
              <strong>{item.title}</strong>
              <small className={`admin-status-${item.status}`}>{item.status}</small>
            </div>
            <div className="admin-script-actions">
              <LinkOrDisabled href={scriptHref}>Script</LinkOrDisabled>
              <LinkOrDisabled href={narrationHref}>Narration</LinkOrDisabled>
              <LinkOrDisabled href={checklistHref}>Checklist</LinkOrDisabled>
              <LinkOrDisabled href={approveHref}>Approve</LinkOrDisabled>
            </div>
          </div>
        )
      })}
    </div>
  )
}
