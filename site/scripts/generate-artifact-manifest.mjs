import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import { readJson } from './validation-helpers.mjs'

const root = process.cwd()
const output = 'artifact-manifest.json'
const excludedDirectories = new Set(['.git', 'node_modules', '.output', 'dist', '.tanstack', '.tanstack-start', '__pycache__', '.pytest_cache'])

function collect(directory = '.') {
  const results = []
  for (const entry of fs.readdirSync(path.join(root, directory), { withFileTypes: true })) {
    const relativePath = path.posix.join(directory === '.' ? '' : directory, entry.name)
    if (entry.isDirectory()) {
      if (!excludedDirectories.has(entry.name)) results.push(...collect(relativePath))
      continue
    }
    if (relativePath === output) continue
    results.push(relativePath)
  }
  return results.sort()
}

const files = collect().map((relativePath) => {
  const bytes = fs.readFileSync(path.join(root, relativePath))
  return {
    path: relativePath,
    bytes: bytes.length,
    sha256: crypto.createHash('sha256').update(bytes).digest('hex'),
  }
})

const questions = readJson('content/questions.json')
const zones = readJson('content/zones.json')
const creatures = readJson('content/creatures.json')
const sources = readJson('content/sources.json')
const videoQueue = readJson('production/video-queue.json')

const manifest = {
  artifact: 'How We Know',
  repository: 'how-we-know',
  version: '1.4.0',
  generatedAt: new Date().toISOString(),
  validationStatus: 'STRUCTURALLY CHECKED — LOCAL VALIDATION REQUIRED',
  implementedPhases: [
    'Research Phase 0',
    'Site Phases 1-4',
    'Measurement Phase structural implementation',
    'Channel Phase 1 production foundation',
    'Channel Phase 2 final script system',
    'Channel Phase 3 batch assembly line',
    'Channel Phase 4 publishing and reciprocal-link contract',
    'Channel Phase 5 twenty-video release packages',
    'Optional local TTS, FFmpeg render, upload and sync automation',
    'Provider-gated Cloudflare Workers deployment',
    'Credentialless noindex owner operations guide at /admin',
    'Exact GitHub workflow, file, folder, receipt and runbook links',
    'Receipt-backed human-pass approval GitHub workflow',
    'Static snapshot readiness generation for twenty videos',
    'Twenty-script humanization pass with unique cold opens, POV drafts, evidence limits and structural variation',
    'Exhaustive digit-bearing sentence source mapping and anti-template validation',
    'Local eSpeak/FFmpeg technical proof marked not final',
    'GitHub Actions Kokoro voice audition and twenty-video final-render activation',
    'YouTube OAuth refresh-token and scheduled batch-upload activation',
  ],
  counts: {
    files: files.length,
    questions: questions.length,
    zones: zones.length,
    creatures: creatures.length,
    sources: sources.length,
    publicRoutes: 9 + questions.length + zones.length + creatures.length,
    prerenderRoutes: 10 + questions.length + zones.length + creatures.length,
    initialVideoQueue: videoQueue.length,
    finalVideoScripts: readJson('production/scripts/index.json').length,
    admittedMediaAssets: readJson('production/asset-rights-manifest.json').length,
    originalMusicBeds: 4,
    originalMotionClips: 20,
    thumbnailRenders: 20,
  },
  unprovenBoundaries: [
    'npm dependency installation and package-lock creation',
    'Framework-aware TypeScript semantic typecheck',
    'TanStack Start production build and prerendered HTML inspection',
    'Browser and deployed Cloudflare Workers journeys, including responsive /admin review',
    'Owner confirmation that every drafted first-person observation is personally true',
    'Human approval of the selected Kokoro voice and speed',
    'Live dispatch, commit and push from the human-pass approval workflow',
    'Execution of the internet-enabled GitHub Actions Kokoro runner',
    'Twenty generated Kokoro WAVs and twenty public-review MP4 outputs',
    'YouTube OAuth upload, publication and public video metadata',
    'Analytics, Search Console, indexation, ranking, backlink and citation telemetry',
  ],
  hashAlgorithm: 'SHA-256',
  manifestSelfHash: 'excluded to avoid circular hashing',
  files,
}

fs.writeFileSync(path.join(root, output), `${JSON.stringify(manifest, null, 2)}\n`)
console.log(`Generated ${output} for ${files.length} files.`)
