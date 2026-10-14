import type { QueryClient } from '@tanstack/react-query'

/** Todo resultado pessoal atualiza as mesmas projeções, inclusive a última revisão. */
export async function invalidateStudy(client: QueryClient) {
  await Promise.all(['review', 'progress', 'today', 'skills', 'course-completion', 'writing-history']
    .map((key) => client.invalidateQueries({ queryKey: [key] })))
}
