import { useQuery } from '@tanstack/react-query'
import { api } from './client'

function completionError(status: number | undefined): Error {
  if (status === 404) return new Error('Este curso publicado não existe.')
  if (status === undefined) {
    return new Error('Não foi possível falar com a API para buscar a conclusão do curso.')
  }
  return new Error(`A API respondeu ${status} ao buscar a conclusão do curso.`)
}

export function useCourseCompletion(courseSlug: string) {
  return useQuery({
    queryKey: ['course-completion', courseSlug],
    queryFn: async () => {
      const { data, response } = await api.GET(
        '/api/courses/{course_slug}/completion',
        { params: { path: { course_slug: courseSlug } } },
      )
      if (!data) throw completionError(response?.status)
      return data
    },
    enabled: Boolean(courseSlug),
    staleTime: 0,
  })
}
