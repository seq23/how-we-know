import { tanstackStart } from '@tanstack/react-start/plugin/vite'
import { defineConfig } from 'vite'
import viteReact from '@vitejs/plugin-react'
import { nitro } from 'nitro/vite'
import questions from './content/questions.json'
import zones from './content/zones.json'
import creatures from './content/creatures.json'

const activeMethodIds = [...new Set(questions.map((item) => item.method))]

const staticPaths = [
  '/',
  '/questions',
  '/zones',
  '/creatures',
  '/watch',
  '/explore',
  '/methods',
  ...activeMethodIds.map((id) => `/methods/${id}`),
  '/methodology',
  '/editorial-policy',
  '/privacy',
  '/terms',
  '/admin',
  '/404',
  ...questions.map((item) => `/questions/${item.slug}`),
  ...zones.map((item) => `/zones/${item.slug}`),
  ...creatures.map((item) => `/creatures/${item.slug}`),
]

export default defineConfig({
  server: { port: 3000 },
  resolve: { tsconfigPaths: true },
  plugins: [
    tanstackStart({
      srcDirectory: 'src',
      prerender: {
        enabled: true,
        autoSubfolderIndex: true,
        autoStaticPathsDiscovery: true,
        crawlLinks: true,
        failOnError: true,
        retryCount: 2,
      },
      pages: staticPaths.map((path) => ({ path, prerender: { enabled: true } })),
    }),
    viteReact(),
    nitro(),
  ],
})
