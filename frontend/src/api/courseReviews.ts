import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { CourseReviewAttemptInput } from './client'
import { api } from './client'

function reviewError(status: number | undefined): Error {
  if (status === 404) return new Error('Este checkpoint não existe nesta unidade.')
  if (status === 409) return new Error('O conteúdo mudou. Recarregue o checkpoint e tente novamente.')
  if (status === undefined) return new Error('Não foi possível falar com a API do checkpoint.')
  return new Error(`A API respondeu ${status} ao processar o checkpoint.`)
}

export function useCourseReview(courseSlug: string, unitSlug: string) {
  return useQuery({
    queryKey: ['course-review', courseSlug, unitSlug],
    queryFn: async () => {
      const { data, response } = await api.GET(
        '/api/courses/{course_slug}/units/{unit_slug}/review',
        { params: { path: { course_slug: courseSlug, unit_slug: unitSlug } } },
      )
      if (!data) throw reviewError(response?.status)
      return data
    },
    enabled: Boolean(courseSlug && unitSlug),
  })
}

export function useSubmitCourseReview(courseSlug: string, unitSlug: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationKey: ['course-review-attempt', courseSlug, unitSlug],
    mutationFn: async (input: CourseReviewAttemptInput) => {
      const { data, response } = await api.POST(
        '/api/courses/{course_slug}/units/{unit_slug}/review/attempts',
        {
          params: { path: { course_slug: courseSlug, unit_slug: unitSlug } },
          body: input,
        },
      )
      if (!data) throw reviewError(response?.status)
      return data
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: ['course-review', courseSlug, unitSlug],
        }),
        queryClient.invalidateQueries({
          queryKey: ['course-completion', courseSlug],
        }),
        queryClient.invalidateQueries({ queryKey: ['today'] }),
      ])
    },
  })
}
