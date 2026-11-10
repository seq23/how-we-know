/**
 * b3: hub pages list their records as cards, and each card's H2 was the bare record
 * name, so /creatures/, /zones/ and /methods/ had no question heading anywhere
 * (Search Readiness quality sample, 10 Nov 2026). Each card's summary answers
 * "what is it", so the heading asks exactly that. Guarded on the build by
 * scripts/validate-built-html.mjs (every page with two or more H2s has a question).
 */
const lowerFirst = (name: string) => name.charAt(0).toLowerCase() + name.slice(1)
const article = (noun: string) => (/^[aeiou]/iu.test(noun) ? 'an' : 'a')

export const creatureHeading = (name: string) => {
  const noun = lowerFirst(name)
  return `What is ${article(noun)} ${noun}?`
}

export const zoneHeading = (name: string) => `What is the ${name}?`

export const methodHeading = (name: string) => `What does “${lowerFirst(name)}” mean?`
