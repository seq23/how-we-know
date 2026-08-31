/**
 * Guards the legal pages that the YouTube API Services audit is filed against.
 *
 * WHY THIS EXISTS. Google's Audit and Quota Extension Form is graded on
 * screenshots of specific policy content. If any one of these elements silently
 * disappears in a refactor, the audit fails and nobody finds out until a
 * reviewer says no. Every requirement below traces to a clause of the YouTube
 * API Services Developer Policies:
 *
 *   III.A.1    display a link to https://www.youtube.com/t/terms, and state in
 *              the client's own terms that users agree to be bound by them
 *   III.A.2.b  notify users that the API Client uses YouTube API Services
 *   III.A.2.c  reference and link to the Google Privacy Policy
 *   III.A.2.d  explain what API Data is accessed, collected, stored and used
 *   III.A.2.g  disclose cookie / device-storage behaviour
 *   III.A.2.h  explain revocation via the Google security settings page
 *   III.A.2.i  explain how to contact the developer with questions/complaints
 *   III.E.4    the 30-day refresh-or-delete rule for stored API Data
 *   III.D.2.a  deletion within 7 days of revocation
 *
 * It asserts against the ROUTE SOURCE, not the build output, so a broken policy
 * fails the build gate before anything is deployed. The deployed bytes are
 * separately checked over HTTPS by scripts/validate-live-canonicals.mjs's
 * sibling run of this file (`node scripts/validate-legal-policy.mjs --live`).
 *
 * Rule 0: this file hard-fails if its own check set is empty, so it can never
 * exit 0 having examined nothing.
 */
import fs from 'node:fs'
import { assert, readJson } from './validation-helpers.mjs'

const flags = readJson('site-flags.json')
const live = process.argv.includes('--live')

/**
 * Every element the audit and the developer policies require, as a literal that
 * must appear in the page. Adding a requirement here is the whole maintenance
 * story: it is then enforced on both the source and the deployed HTML.
 */
const PRIVACY_REQUIREMENTS = [
  { id: 'youtube-tos-link', clause: 'III.A.1', needle: 'https://www.youtube.com/t/terms', label: 'link to the YouTube Terms of Service' },
  { id: 'google-privacy-link', clause: 'III.A.2.c', needle: 'https://policies.google.com/privacy', label: "link to Google's Privacy Policy" },
  { id: 'uses-api-services', clause: 'III.A.2.b', needle: 'uses YouTube API Services', label: 'statement that the client uses YouTube API Services' },
  { id: 'api-services-heading', clause: 'III.A.2.a', needle: '<h2>YouTube API Services</h2>', label: 'a dedicated YouTube API Services section heading' },
  { id: 'scopes-disclosed', clause: 'III.A.2.d', needle: 'youtube.upload', label: 'disclosure of the authorisation scopes requested' },
  { id: 'scopes-readonly', clause: 'III.A.2.d', needle: 'youtube.readonly', label: 'disclosure of the read scope requested' },
  { id: 'retention-30-day', clause: 'III.E.4', needle: '30 calendar days', label: 'the 30-day refresh-or-delete retention rule' },
  { id: 'cookies-disclosed', clause: 'III.A.2.g', needle: '<h3>Cookies and device storage</h3>', label: 'the cookie / device-storage disclosure' },
  { id: 'revocation-link', clause: 'III.A.2.h', needle: 'https://myaccount.google.com/permissions', label: 'the access-revocation link' },
  { id: 'revocation-link-alt', clause: 'III.A.2.h', needle: 'security.google.com/settings/security/permissions', label: 'the Google security settings revocation URL' },
  { id: 'deletion-section', clause: 'III.D.2.a', needle: '<h2>Data deletion</h2>', label: 'a dedicated data-deletion section' },
  { id: 'deletion-7-day', clause: 'III.D.2.a', needle: '7 calendar days', label: 'the 7-day post-revocation deletion commitment' },
  { id: 'contact-section', clause: 'III.A.2.i', needle: '<h2>Questions, complaints, and deletion requests</h2>', label: 'the contact route for questions and deletion requests' },
]

const TERMS_REQUIREMENTS = [
  { id: 'youtube-tos-link', clause: 'III.A.1', needle: 'https://www.youtube.com/t/terms', label: 'link to the YouTube Terms of Service' },
  { id: 'agree-to-be-bound', clause: 'III.A.1', needle: 'agree to be bound by the', label: "the 'agree to be bound by the YouTube Terms of Service' statement" },
  { id: 'google-privacy-link', clause: 'III.A.2.c', needle: 'https://policies.google.com/privacy', label: "link to Google's Privacy Policy" },
  { id: 'privacy-cross-link', clause: 'audit form', needle: 'href="/privacy"', label: 'a link from the terms to the privacy policy' },
]

// The audit form requires a homepage screenshot showing the policy link, so the
// links must be on the homepage itself. Both live in the shared footer.
const HOMEPAGE_LINK_REQUIREMENTS = [
  { id: 'footer-privacy', clause: 'audit form', needle: 'href="/privacy"', label: 'a privacy policy link on every page including the homepage' },
  { id: 'footer-terms', clause: 'audit form', needle: 'href="/terms"', label: 'a Terms of Service link on every page including the homepage' },
]

const SOURCE_TARGETS = [
  { name: '/privacy', file: 'src/routes/privacy.tsx', requirements: PRIVACY_REQUIREMENTS },
  { name: '/terms', file: 'src/routes/terms.tsx', requirements: TERMS_REQUIREMENTS },
  { name: 'site footer', file: 'src/components/SiteFooter.tsx', requirements: HOMEPAGE_LINK_REQUIREMENTS },
]

// Every needle above is chosen to appear VERBATIM in both the JSX source and the
// server-rendered HTML, so one literal guards both surfaces and there is no
// transformation step to get subtly wrong. (An earlier version stripped tags off
// the needle before searching the source; `Data deletion</h2>` then degraded to
// `Data deletion`, which also matched the cross-reference link further down the
// page — so deleting the heading still passed. Hence: no transformation.)
// Whitespace is collapsed on both sides because JSX wraps lines mid-sentence.
const normalise = (value) => value.replace(/\s+/gu, ' ')

const failures = []
let checked = 0

if (!live) {
  for (const target of SOURCE_TARGETS) {
    assert(fs.existsSync(target.file), `Legal-page validation: ${target.file} does not exist`)
    const source = normalise(fs.readFileSync(target.file, 'utf8'))
    assert(target.requirements.length > 0, `Legal-page validation resolved zero requirements for ${target.name}`)
    for (const requirement of target.requirements) {
      checked += 1
      if (!source.includes(requirement.needle)) {
        failures.push(
          `${target.name} (${target.file}) is missing ${requirement.label} ` +
            `[id: ${requirement.id}, policy clause ${requirement.clause}, expected literal: ${requirement.needle}]`,
        )
      }
    }
  }
} else {
  const origin = process.env.LIVE_ORIGIN || flags.canonicalOrigin
  const LIVE_TARGETS = [
    { name: `${origin}/privacy/`, url: new URL('/privacy/', origin).toString(), requirements: PRIVACY_REQUIREMENTS },
    { name: `${origin}/terms/`, url: new URL('/terms/', origin).toString(), requirements: TERMS_REQUIREMENTS },
    { name: `${origin}/ (homepage)`, url: new URL('/', origin).toString(), requirements: HOMEPAGE_LINK_REQUIREMENTS },
  ]
  for (const target of LIVE_TARGETS) {
    const response = await fetch(target.url, { headers: { 'user-agent': 'how-we-know-validator' } })
    if (response.status !== 200) {
      failures.push(`${target.name} returned HTTP ${response.status}`)
      continue
    }
    const html = normalise(await response.text())
    assert(target.requirements.length > 0, `Legal-page validation resolved zero requirements for ${target.name}`)
    for (const requirement of target.requirements) {
      checked += 1
      if (!html.includes(requirement.needle)) {
        failures.push(
          `${target.name} is missing ${requirement.label} ` +
            `[id: ${requirement.id}, policy clause ${requirement.clause}, expected literal: ${requirement.needle}]`,
        )
      }
    }
  }
}

assert(
  failures.length === 0,
  `YouTube API Services policy requirements are not satisfied:\n  - ${failures.join('\n  - ')}`,
)

// Rule 0. A validator that examined nothing — or only part of the set — must
// never report success.
const expected = SOURCE_TARGETS.reduce((total, target) => total + target.requirements.length, 0)
assert(checked > 0, 'Legal-page validation examined zero elements')
assert(
  checked === expected,
  `Legal-page validation examined ${checked} of ${expected} required elements; the check set was truncated`,
)

// A NAMED STOP, not a silent pass: the one required element that cannot be
// satisfied by code, only by the owner choosing an address to publish.
const contactNote = flags.privacyContactEmail
  ? `contact address published (${flags.privacyContactEmail})`
  : 'NAMED STOP: privacyContactEmail is empty in site-flags.json, so /privacy and /terms publish no ' +
    'contact address. Developer Policy III.A.2.i requires one and the audit form checks for it. ' +
    'Set site-flags.json > privacyContactEmail, rebuild, redeploy.'

console.log(
  `Legal-policy validation passed (${checked} required elements present across ` +
    `${live ? 'the deployed pages' : 'the route sources'}). ${contactNote}`,
)
