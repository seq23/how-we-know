// ONE RULE FOR EVERY LENGTH CHECK ON THE SITE (owner, 2 Nov 2026: "No petty
// validation ... over a word limit never fails; under one fails only below 75%
// of it"). Over a limit: a note. Under a floor: a note down to 75% of it, a
// failure only below that.
export const FLOOR_FRACTION = 0.75

/** The hard minimum for a nominal floor. */
export const hardFloor = (floor) => Math.ceil(floor * FLOOR_FRACTION)

/** 'fail' below 75% of the floor, 'note' below the floor or over the max, else 'ok'. */
export function lengthVerdict(n, floor, max = Infinity) {
  if (n < hardFloor(floor)) return 'fail'
  if (n < floor || n > max) return 'note'
  return 'ok'
}
