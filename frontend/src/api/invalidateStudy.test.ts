import { QueryClient } from '@tanstack/react-query'
import { expect, it } from 'vitest'
import { invalidateStudy } from './invalidateStudy'

it('invalida todas as projeções pessoais sem esperar expirar o cache de cinco minutos', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: 300_000 } } })
  const prefixes = ['review', 'progress', 'today', 'skills', 'course-completion', 'writing-history']
  for (const key of [...prefixes, 'lesson']) client.setQueryData([key, 'voa-level-1'], { old: true })
  await invalidateStudy(client)
  for (const key of prefixes) expect(client.getQueryState([key, 'voa-level-1'])?.isInvalidated).toBe(true)
  expect(client.getQueryState(['lesson', 'voa-level-1'])?.isInvalidated).toBe(false)
  client.clear()
})
