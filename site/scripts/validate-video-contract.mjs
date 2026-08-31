import { assert, isHttpsUrl, isIsoDate, readJson } from './validation-helpers.mjs'

const questions = readJson('content/questions.json')
const queue = readJson('production/video-queue.json')
const allowedStatuses = new Set(['unplanned', 'planned', 'in-production', 'published'])
const requiredPublishedFields = [
  'videoId',
  'title',
  'descriptionFirstLine',
  'thumbnailUrl',
  'uploadDate',
  'duration',
  'transcript',
]

for (const question of questions) {
  const video = question.video
  assert(allowedStatuses.has(video.status), `${question.slug} has invalid video status ${video.status}`)
  assert(Array.isArray(video.chapters), `${question.slug} video chapters must be an array`)

  if (video.status === 'published') {
    for (const field of requiredPublishedFields) {
      assert(
        typeof video[field] === 'string' && video[field].trim(),
        `${question.slug} published video is missing ${field}`,
      )
    }
    assert(video.title === question.question, `${question.slug} video title must preserve the exact query`)
    assert(
      video.descriptionFirstLine === question.directAnswer,
      `${question.slug} first video-description line must match the canonical direct answer`,
    )
    assert(isHttpsUrl(video.thumbnailUrl), `${question.slug} thumbnail must be an HTTPS URL`)
    assert(isIsoDate(video.uploadDate), `${question.slug} uploadDate must be YYYY-MM-DD`)
    assert(/^PT(?=\d)(?:\d+H)?(?:\d+M)?(?:\d+S)?$/.test(video.duration), `${question.slug} duration is not ISO 8601`)
    assert(video.transcript.trim().split(/\s+/).length >= 500, `${question.slug} transcript is too short`)
    assert(video.chapters.length >= 2, `${question.slug} published video needs chapters`)
  } else {
    assert(video.videoId === null, `${question.slug} unpublished video must not have a videoId`)
  }
}

assert(queue.length === 20, `Expected 20 videos in the launch queue, found ${queue.length}`)
for (const item of queue) {
  const question = questions.find((record) => record.slug === item.articleSlug)
  assert(question, `Queue item ${item.sequence} has no canonical question record`)
  assert(item.query === question.question, `Queue item ${item.sequence} query drifts from its article H1`)
  assert(item.articlePath === `/questions/${question.slug}`, `Queue item ${item.sequence} has the wrong article path`)
  assert(item.videoId === question.video.videoId, `Queue item ${item.sequence} video ID drifts from the canonical record`)
}

console.log('Cross-surface video contract validation passed.')
