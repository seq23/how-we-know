/// <reference types="vite/client" />
import { HeadContent, Scripts, createRootRoute } from '@tanstack/react-router'
import type { ReactNode } from 'react'
import appCss from '~/styles/app.css?url'
import { SiteHeader } from '~/components/SiteHeader'
import { SiteFooter } from '~/components/SiteFooter'
import { ErrorBoundary } from '~/components/ErrorBoundary'
import { Analytics } from '~/components/Analytics'
import { NotFound } from '~/components/NotFound'
import { jsonLdScript, organizationSchema, websiteSchema } from '~/lib/schema'
import { searchIndexingEnabled, site } from '~/lib/site'

export const Route = createRootRoute({
  head:()=>({ meta:[{charSet:'utf-8'},{name:'viewport',content:'width=device-width, initial-scale=1'},{title:site.name},{name:'description',content:site.description},{name:'theme-color',content:site.themeColor},...(searchIndexingEnabled?[]:[{name:'robots',content:'noindex,follow'}])], links:[{rel:'stylesheet',href:appCss},{rel:'icon',href:'/favicon.svg',type:'image/svg+xml'},{rel:'manifest',href:'/site.webmanifest'}], scripts:[jsonLdScript(organizationSchema),jsonLdScript(websiteSchema)] }),
  errorComponent:ErrorBoundary, notFoundComponent:NotFound, shellComponent:RootDocument,
})
function RootDocument({children}:{children:ReactNode}) { return <html lang="en"><head><HeadContent/></head><body><a className="skip-link" href="#main-content">Skip to content</a><SiteHeader/><div id="main-content">{children}</div><SiteFooter/><Analytics/><Scripts/></body></html> }
