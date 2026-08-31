import { createFileRoute, notFound } from '@tanstack/react-router'
import { getQuestionBySlug } from '~/lib/questions-data'
import { QuestionPage } from '~/components/QuestionPage'
import { pageMeta } from '~/lib/seo'
import { articleSchema, breadcrumbSchema, faqSchema, jsonLdScript, videoSchema } from '~/lib/schema'

export const Route = createFileRoute('/questions/$question')({
  loader: ({ params }) => {
    const record = getQuestionBySlug(params.question)
    if (!record) throw notFound()
    return record
  },
  head: ({ loaderData }) => {
    if (!loaderData) return {}
    const record = loaderData
    const video = videoSchema(record)
    return {
      ...pageMeta(record.question, record.description, `/questions/${record.slug}`, 'article'),
      scripts: [
        jsonLdScript(articleSchema(record)),
        jsonLdScript(faqSchema(record)),
        jsonLdScript(
          breadcrumbSchema([
            { name: 'Home', path: '/' },
            { name: 'Questions', path: '/questions' },
            { name: record.question, path: `/questions/${record.slug}` },
          ]),
        ),
        ...(video ? [jsonLdScript(video)] : []),
      ],
    }
  },
  component: QuestionRoute,
})

function QuestionRoute() {
  const record = Route.useLoaderData()
  return <QuestionPage record={record} />
}
