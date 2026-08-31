import adminStatus from '../../content/admin-status.json'

export type AdminStatus = typeof adminStatus

export const adminSnapshot = adminStatus

export const defaultGithubRepository = import.meta.env.VITE_GITHUB_REPOSITORY || ''
export const defaultGithubBranch = import.meta.env.VITE_GITHUB_BRANCH || 'main'

export function normalizeGithubRepository(value: string) {
  return value
    .trim()
    .replace(/^https?:\/\/github\.com\//, '')
    .replace(/\.git$/, '')
    .replace(/^\/+|\/+$/g, '')
}

export function isGithubRepository(value: string) {
  return /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(normalizeGithubRepository(value))
}

export function githubHref(
  repository: string,
  kind: 'repo' | 'actions' | 'workflow' | 'blob' | 'edit' | 'tree',
  target = '',
  branch = defaultGithubBranch,
) {
  const normalized = normalizeGithubRepository(repository)
  if (!isGithubRepository(normalized)) return ''
  const base = `https://github.com/${normalized}`
  if (kind === 'repo') return base
  if (kind === 'actions') return `${base}/actions`
  if (kind === 'workflow') return `${base}/actions/workflows/${target}`
  return `${base}/${kind}/${branch}/${target}`
}
