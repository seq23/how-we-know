import fs from 'node:fs'
import path from 'node:path'

const root = process.cwd()
const readJson = (relativePath, fallback = null) => {
  const file = path.join(root, relativePath)
  return fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : fallback
}
const countFiles = (relativePath, extension) => {
  const directory = path.join(root, relativePath)
  if (!fs.existsSync(directory)) return 0
  return fs.readdirSync(directory).filter((name) => name.endsWith(extension)).length
}

const narrator = readJson('production/narrator-selection.json', {})
const ledger = readJson('production/human-pass/approval-ledger.json', [])
const queue = readJson('production/video-queue.json', [])
const questions = readJson('content/questions.json', [])
const receiptsDirectory = path.join(root, 'production/provider-receipts/youtube')
const receipts = fs.existsSync(receiptsDirectory)
  ? fs
      .readdirSync(receiptsDirectory)
      .filter((name) => name.endsWith('.json'))
      .map((name) => readJson(`production/provider-receipts/youtube/${name}`, {}))
  : []

const approved = ledger.filter((item) => item.status === 'approved').length
const narrationWavs = countFiles('production/audio/narration', '.wav')
const renderedMp4s = countFiles('production/outputs', '.mp4')
const liveIds = receipts.filter((receipt) => typeof receipt.videoId === 'string' && receipt.videoId.trim()).length
const publishedVideos = questions.filter((question) => question.video?.status === 'published' && question.video?.videoId).length
const narratorApproved = narrator.status === 'human-approved'

const releaseReady =
  narratorApproved &&
  approved === ledger.length &&
  narrationWavs >= ledger.length &&
  renderedMp4s >= ledger.length

const items = ledger.map((item) => {
  const queueItem = queue.find((candidate) => Number(candidate.sequence) === Number(item.sequence))
  const prefix = String(item.sequence).padStart(2, '0')
  return {
    sequence: item.sequence,
    slug: item.slug,
    title: queueItem?.query || item.slug,
    status: item.status,
    finalScriptPath: `production/scripts/final/${prefix}-${item.slug}.md`,
    plaintextPath: item.scriptPath,
    humanPassPath: item.humanPassPath,
  }
})

const payload = {
  narrator: {
    state: narratorApproved ? 'ready' : 'pending',
    label: narratorApproved ? `${narrator.voice} at ${narrator.speed}` : 'Audition pending',
    voice: narrator.voice || null,
    speed: narrator.speed || null,
  },
  humanPass: {
    approved,
    total: ledger.length,
    pending: ledger.length - approved,
    items,
  },
  production: {
    narrationWavs,
    renderedMp4s,
    renderReceiptPresent: fs.existsSync(path.join(root, 'production/outputs/render-receipt.json')),
  },
  youtube: {
    receiptFiles: receipts.length,
    liveIds,
  },
  site: {
    publishedVideos,
  },
  releaseGate: {
    state: releaseReady ? 'ready' : 'blocked',
    label: releaseReady ? 'Ready for provider review' : 'Blocked pending human/runtime work',
  },
}

fs.writeFileSync(path.join(root, 'content/admin-status.json'), `${JSON.stringify(payload, null, 2)}\n`)
console.log(`Generated credentialless admin snapshot (${approved}/${ledger.length} scripts approved).`)
