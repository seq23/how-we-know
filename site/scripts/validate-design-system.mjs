import fs from 'node:fs'
import { assert } from './validation-helpers.mjs'

const css = fs.readFileSync('src/styles/app.css', 'utf8')
const rootEnd = css.indexOf('}')
assert(rootEnd > 0, 'CSS is missing a :root token block')
const runtimeCss = css.slice(rootEnd + 1)
assert(
  !/(?:#[0-9a-fA-F]{3,8}|rgba?\(|hsla?\()/u.test(runtimeCss),
  'Runtime CSS contains a hardcoded color outside the semantic token block',
)
assert(css.includes('--font-display:'), 'Display typography token is missing')
assert(css.includes('--font-body:'), 'Body typography token is missing')
assert(css.includes('.skip-link'), 'Keyboard skip link styling is missing')

for (const file of fs.readdirSync('src/routes').filter((name) => name.endsWith('.tsx'))) {
  const source = fs.readFileSync(`src/routes/${file}`, 'utf8')
  assert(!/style=\{\{[^}]*color/u.test(source), `${file} contains an inline hardcoded color`)
}

console.log('Design-token validation passed.')
