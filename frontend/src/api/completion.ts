import { useQuery } from '@tanstack/react-query'
import { api } from './client'
import { ApiError } from './errors'

export function useCourseCompletion(courseSlug: string) {
  return useQuery({
    queryKey: ['course-completion', courseSlug],
    queryFn: async () => {
      const { data, response } = await api.GET(
        '/api/courses/{course_slug}/completion',
        { params: { path: { course_slug: courseSlug } } },
      )
      if (!data) throw new ApiError('a conclusão do curso', response)
      return data
    },
    enabled: Boolean(courseSlug),
    staleTime: 0,
  })
}
