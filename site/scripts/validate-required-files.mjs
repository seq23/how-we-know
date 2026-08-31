import fs from 'node:fs'
import { assert } from './validation-helpers.mjs'

const required = [
  'README.md',
  'package.json',
  'artifact-manifest.json',
  'tsconfig.json',
  'vite.config.ts',
  '.env.example',
  'content/questions.json',
  'content/sources.json',
  'content/zones.json',
  'content/creatures.json',
  'content/traffic-sources.json',
  'content/admin-status.json',
  'src/routes/admin.tsx',
  'src/lib/admin.ts',
  '.github/workflows/approve-human-pass.yml',
  'scripts/generate-admin-status.mjs',
  'scripts/validate-admin.mjs',
  'scripts/validate-legal-policy.mjs',
  'src/routes/privacy.tsx',
  'src/routes/terms.tsx',
  'docs/runbooks/ADMIN_OPERATIONS_GUIDE.md',
  'data/measurement/kpi-contract.json',
  'data/measurement/observations.json',
  'docs/architecture.md',
  'docs/content-contract.md',
  'docs/deployment.md',
  'docs/phase-ledger.md',
  'docs/research-provenance.md',
  'docs/scope-receipt.md',
  'docs/validation.md',
  'docs/measurement.md',
  'production/asset-rights-manifest.json',
  'production/asset-rights-manifest.schema.json',
  'production/candidate-footage-sources.json',
  'production/narrator-evaluation.md',
  'production/script-template.md',
  'production/editing-template-spec.md',
  'production/thumbnail-template-spec.md',
  'production/weekly-production-runbook.md',
  'production/video-queue.json',
  'production/sync-checklist.md',
  'docs/runbooks/HUMANIZED_SCRIPT_AND_RENDER_GATE.md',
  'production/proofs/01-humanized-technical-proof-receipt.json',
  'production/proofs/01-humanized-technical-proof.wav',
  'production/proofs/01-humanized-technical-proof.mp4',
  'production/research/number-verification-exhaustive.json',
  'production/research/number-verification-exhaustive.md',
  'production/research/number-verification.md',
  'production/research/humanization-audit.json',
  'production/research/humanization-audit.md',
]
for (const file of required) assert(fs.existsSync(file), `Missing required artifact: ${file}`)

const unresolved = []
for (const directory of ['src', 'content', 'production', 'docs', 'scripts']) {
  for (const entry of fs.readdirSync(directory, { recursive: true, withFileTypes: true })) {
    if (!entry.isFile()) continue
    const file = `${entry.parentPath}/${entry.name}`
    if (file.endsWith('scripts/validate-required-files.mjs')) continue
    const text = fs.readFileSync(file, 'utf8')
    if (/\b(?:TODO|FIXME|CHANGEME|LOREM IPSUM)\b/i.test(text)) unresolved.push(file)
  }
}
assert(unresolved.length === 0, `Unresolved implementation markers found: ${unresolved.join(', ')}`)

console.log('Required-artifact validation passed.')
