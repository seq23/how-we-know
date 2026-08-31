import fs from 'node:fs'
import path from 'node:path'

export const root = process.cwd()

export function readJson(relativePath) {
  return JSON.parse(fs.readFileSync(path.join(root, relativePath), 'utf8'))
}

export function assert(condition, message) {
  if (!condition) throw new Error(message)
}

export function assertUnique(values, label) {
  const seen = new Set()
  for (const value of values) {
    assert(!seen.has(value), `Duplicate ${label}: ${value}`)
    seen.add(value)
  }
}

export function wordCount(value) {
  return value.trim().split(/\s+/).filter(Boolean).length
}

export function isIsoDate(value) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(`${value}T00:00:00Z`))
}

export function isHttpsUrl(value) {
  try {
    return new URL(value).protocol === 'https:'
  } catch {
    return false
  }
}
