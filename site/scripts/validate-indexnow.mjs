/**
 * The IndexNow key file, guarded.
 *
 * IndexNow proves ownership by asking the host to serve the key a submission was
 * signed with. So two things can silently break the whole mechanism, and neither
 * shows up anywhere else:
 *
 *   - the key file disappears from public/ (nothing else reads it, so every
 *     submission is rejected and the build stays green), or
 *   - the key is rotated in site-flags.json and the OLD file is left behind, so
 *     the host proves a key nobody submits with.
 *
 * Search readiness items e3 and i8 (owner's checklist, 25 Oct 2026) are this file
 * existing and being served. This validator reads the flag and the directory, and
 * the post-deploy live check reads the same key over HTTP from the deployed site.
 *
 * Rule 0: a run that examined zero key files fails.
 */
import fs from 'node:fs'
import path from 'node:path'
import { assert, readJson, root } from './validation-helpers.mjs'

const flags = readJson('site-flags.json')
const key = flags.indexNowKey

assert(
  /^[0-9a-f]{32,64}$/.test(String(key ?? '')),
  `site-flags.json indexNowKey must be 32-64 lowercase hex characters; got ${JSON.stringify(key)}`,
)

const publicDir = path.join(root, 'public')
const keyFiles = fs.readdirSync(publicDir).filter((entry) => /^[0-9a-f]{32,64}\.txt$/.test(entry))

assert(keyFiles.length > 0, 'No IndexNow key file in public/. Run `npm run generate`.')
assert(
  keyFiles.length === 1,
  `public/ serves ${keyFiles.length} IndexNow key files (${keyFiles.join(', ')}). ` +
    'Exactly one key may be provable at a time; `npm run generate` removes the others.',
)
assert(
  keyFiles[0] === `${key}.txt`,
  `public/${keyFiles[0]} does not match site-flags.json indexNowKey (${key}.txt). ` +
    'The host would prove a key no submission is signed with. Run `npm run generate`.',
)

const served = fs.readFileSync(path.join(publicDir, keyFiles[0]), 'utf8').trim()
assert(
  served === key,
  `public/${keyFiles[0]} contains ${JSON.stringify(served)}, not the key it is named for. ` +
    'IndexNow requires the file body to be the key itself.',
)

console.log(`IndexNow validation passed (1 key file, public/${keyFiles[0]}, body matches the flag).`)
