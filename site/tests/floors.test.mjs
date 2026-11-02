import test from 'node:test'
import assert from 'node:assert/strict'
import { lengthVerdict, hardFloor, FLOOR_FRACTION } from '../scripts/floors.mjs'

// Owner, 2 Nov 2026: over a limit never fails; under a floor fails only below 75%.
test('over a limit is a note, never a failure', () => {
  assert.equal(lengthVerdict(90, 30, 65), 'note')
})
test('just under a floor is a note; below 75% of it fails', () => {
  assert.equal(FLOOR_FRACTION, 0.75)
  assert.equal(lengthVerdict(25, 30, 65), 'note')
  assert.equal(lengthVerdict(hardFloor(30) - 1, 30, 65), 'fail')
  assert.equal(lengthVerdict(899, 900), 'note')
  assert.equal(lengthVerdict(600, 900), 'fail')
})
test('inside the band is ok', () => {
  assert.equal(lengthVerdict(40, 30, 65), 'ok')
})
