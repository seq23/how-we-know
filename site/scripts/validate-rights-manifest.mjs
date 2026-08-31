import fs from 'node:fs'
import { assert, isHttpsUrl, readJson } from './validation-helpers.mjs'

const manifest = readJson('production/asset-rights-manifest.json')
const candidates = readJson('production/candidate-footage-sources.json')
assert(Array.isArray(manifest), 'Rights manifest must be an array')
assert(candidates.length >= 5, 'Candidate footage registry is incomplete')

const seen = new Set()
for (const item of manifest) {
  assert(item.assetId && !seen.has(item.assetId), `Duplicate or missing assetId ${item.assetId || 'unknown'}`)
  seen.add(item.assetId)
  assert(/^[a-f0-9]{64}$/.test(item.fileSha256), `Invalid SHA256 for ${item.assetId}`)
  if (item.sourceOrganization === 'How We Know') {
    assert(item.originalUrl === null, `Original asset ${item.assetId} must not fabricate an external URL`)
    assert(item.assetPageUrl === null, `Original asset ${item.assetId} must not fabricate an asset-page URL`)
  } else {
    assert(isHttpsUrl(item.originalUrl), `External asset ${item.assetId} needs an HTTPS original URL`)
    assert(isHttpsUrl(item.assetPageUrl), `External asset ${item.assetId} needs an HTTPS asset-page URL`)
  }
  assert(item.localFilename && fs.existsSync(item.localFilename), `Asset file missing for ${item.assetId}`)
  assert(item.sourceOrganization, `Asset ${item.assetId} needs a source organization`)
  assert(item.rightsBasis, `Asset ${item.assetId} needs a rights basis`)
  if (item.assetStatus === 'approved') {
    assert(item.commercialUseAllowed === true, `Approved asset ${item.assetId} is not cleared for commercial use`)
    assert(item.modificationAllowed === true, `Approved asset ${item.assetId} is not cleared for editing`)
  }
  if (item.attributionRequired) {
    assert(item.requiredCreditText?.trim(), `Attribution text is missing for ${item.assetId}`)
  }
}

for (const source of candidates) {
  assert(source.source && isHttpsUrl(source.url), 'Candidate source needs a name and HTTPS URL')
  assert(source.defaultAdmission, `${source.source} needs a default-admission decision`)
  assert(source.requiredChecks.length >= 2, `${source.source} needs item-level rights checks`)
}

console.log(`Rights-control validation passed (${manifest.length} admitted assets, ${candidates.length} source lanes).`)
