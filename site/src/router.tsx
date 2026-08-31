import { createRouter } from '@tanstack/react-router'
import { routeTree } from './routeTree.gen'
import { ErrorBoundary } from './components/ErrorBoundary'
import { NotFound } from './components/NotFound'
export function getRouter() { return createRouter({ routeTree, defaultPreload:'intent', defaultErrorComponent:ErrorBoundary, defaultNotFoundComponent:NotFound, scrollRestoration:true }) }
