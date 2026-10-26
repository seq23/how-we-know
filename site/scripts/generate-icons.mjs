/**
 * The raster icons and the OG card, rasterised from the SVG sources in public/.
 *
 * Why these files exist at all: /favicon.ico and /apple-touch-icon.png both
 * answered 404 on the live site on 2026-10-25, and the OG card was only ever an
 * SVG. An SVG is not an og:image — no major platform rasterises one for a share
 * preview, and the dimensions cannot be declared for something with no intrinsic
 * pixel size, so og:image:width and og:image:height were missing too. The
 * Organization node's logo had the same problem.
 *
 * Why it is not part of `npm run build`: this needs sharp, which is a native
 * binary that arrives as a transitive dependency rather than a declared one.
 * The four files are committed, and scripts/validate-icons.mjs reads their real
 * bytes — magic number and pixel dimensions, with no dependency at all — so the
 * build proves the artifacts without needing the tool that made them.
 *
 * Re-run after changing public/favicon.svg or public/og-default.svg:
 *   node scripts/generate-icons.mjs
 */
import fs from 'node:fs'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
let sharp
try {
  sharp = require('sharp')
} catch {
  console.error(
    'NAMED STOP: sharp is not installed, so the icons cannot be regenerated here.\n' +
      'The committed PNGs in public/ are still valid; install sharp before changing the SVG sources.',
  )
  process.exit(2)
}

const favicon = fs.readFileSync('public/favicon.svg')
const ogCard = fs.readFileSync('public/og-default.svg')

/**
 * A single-image .ico, built by hand.
 *
 * sharp cannot write .ico, and the format needs no library: a 6-byte ICONDIR, a
 * 16-byte ICONDIRENTRY and then the image. Every browser since IE11 accepts a
 * PNG payload inside that container, and a 32x32 PNG is what every one of them
 * actually wants.
 */
function icoFromPng(png, size) {
  const header = Buffer.alloc(6)
  header.writeUInt16LE(0, 0) // reserved
  header.writeUInt16LE(1, 2) // type: icon
  header.writeUInt16LE(1, 4) // one image
  const entry = Buffer.alloc(16)
  entry.writeUInt8(size === 256 ? 0 : size, 0) // width, 0 means 256
  entry.writeUInt8(size === 256 ? 0 : size, 1) // height
  entry.writeUInt8(0, 2) // palette colours: none, it is truecolour
  entry.writeUInt8(0, 3) // reserved
  entry.writeUInt16LE(1, 4) // colour planes
  entry.writeUInt16LE(32, 6) // bits per pixel
  entry.writeUInt32LE(png.length, 8)
  entry.writeUInt32LE(header.length + entry.length, 12)
  return Buffer.concat([header, entry, png])
}

const written = []
const write = (file, buffer) => {
  fs.writeFileSync(`public/${file}`, buffer)
  written.push(`${file} (${buffer.length} bytes)`)
}

const png32 = await sharp(favicon, { density: 384 }).resize(32, 32).png({ compressionLevel: 9 }).toBuffer()
write('favicon.ico', icoFromPng(png32, 32))

write(
  'apple-touch-icon.png',
  await sharp(favicon, { density: 384 }).resize(180, 180).png({ compressionLevel: 9 }).toBuffer(),
)

write(
  'logo.png',
  await sharp(favicon, { density: 1024 }).resize(512, 512).png({ compressionLevel: 9 }).toBuffer(),
)

write(
  'og-default.png',
  await sharp(ogCard, { density: 96 }).resize(1200, 630).png({ compressionLevel: 9 }).toBuffer(),
)

console.log(`Generated ${written.length} raster assets: ${written.join(', ')}.`)
