import type { ErrorComponentProps } from '@tanstack/react-router'
export function ErrorBoundary({ error }: ErrorComponentProps) { return <main className="shell prose-page"><p className="eyebrow">Page error</p><h1>The dive was interrupted.</h1><p>{error.message}</p><p><a className="button" href="/">Return home</a></p></main> }
