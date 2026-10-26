/**
 * The icons and the OG card are real files of the right kind and size.
 *
 * On 2026-10-25 /favicon.ico and /apple-touch-icon.png both answered 404 on the
 * live site, and the only OG image was an SVG — which no share preview
 * rasterises and which has no pixel dimensions to declare. These four files are
 * committed rather than built (see scripts/generate-icons.mjs), so this reads
 * their actual bytes: the magic number, and for a PNG the width and height out
 * of the IHDR chunk. No dependency, and a wrong-sized file cannot pass.
 */
import fs from 'node:fs'
import { assert } from './validation-helpers.mjs'

const pngSize = (buffer) => {
  assert(
    buffer.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])),
    'file is not a PNG',
  )
  assert(buffer.subarray(12, 16).toString('ascii') === 'IHDR', 'PNG has no IHDR chunk first')
  return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) }
}

const expected = [
  { file: 'public/apple-touch-icon.png', width: 180, height: 180 },
  { file: 'public/logo.png', width: 512, height: 512 },
  { file: 'public/og-default.png', width: 1200, height: 630 },
]

let checked = 0
for (const { file, width, height } of expected) {
  assert(fs.existsSync(file), `Missing raster asset: ${file}`)
  const buffer = fs.readFileSync(file)
  const size = pngSize(buffer)
  assert(
    size.width === width && size.height === height,
    `${file} is ${size.width}x${size.height}, expected ${width}x${height}`,
  )
  checked += 1
}

// The .ico: a 6-byte ICONDIR declaring type 1 and at least one image.
const ico = fs.readFileSync('public/favicon.ico')
assert(ico.length > 100, 'public/favicon.ico is too small to contain an image')
assert(ico.readUInt16LE(0) === 0 && ico.readUInt16LE(2) === 1, 'public/favicon.ico is not an icon file')
assert(ico.readUInt16LE(4) >= 1, 'public/favicon.ico declares no images')
checked += 1

// The root document must actually point at them, or serving them changes nothing.
const root = fs.readFileSync('src/routes/__root.tsx', 'utf8')
assert(root.includes("href:'/favicon.ico'"), 'The root document does not link /favicon.ico')
assert(root.includes("href:'/apple-touch-icon.png'"), 'The root document does not link /apple-touch-icon.png')
assert(root.includes("href:'/site.webmanifest'"), 'The root document does not link /site.webmanifest')

const manifest = JSON.parse(fs.readFileSync('public/site.webmanifest', 'utf8'))
const sources = new Set((manifest.icons ?? []).map((icon) => icon.src))
for (const src of ['/favicon.svg', '/favicon.ico', '/apple-touch-icon.png', '/logo.png']) {
  assert(sources.has(src), `site.webmanifest does not list ${src}`)
}

assert(checked === 4, `Icon validation examined ${checked} assets, expected 4`)
console.log(`Icon validation passed (${checked} raster assets, manifest and root links).`)
