import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type StudySessionInput } from './client'

export function useProgress(courseSlug?: string, unitSlug?: string) {
  return useQuery({
    queryKey: ['progress', courseSlug ?? 'all', unitSlug ?? 'all'],
    queryFn: async () => {
      const { data, response } = await api.GET('/api/me/progress', {
        params: { query: { course: courseSlug, unit: unitSlug } },
      })
      if (!data) throw new Error(`A API respondeu ${response?.status ?? 'nada'} ao buscar progresso.`)
      return data
    },
    staleTime: 0,
  })
}

/** Marca ou desmarca uma aula; a lista de progresso é invalidada em seguida. */
export function useMarcarEstudada(courseSlug: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ numero, estudada }: { numero: number; estudada: boolean }) => {
      const op = estudada ? api.PUT : api.DELETE
      const { response } = await op('/api/courses/{course_slug}/lessons/{number}/studied', {
        params: { path: { course_slug: courseSlug, number: numero } },
      })
      if (!response?.ok) throw new Error('Não foi possível salvar a marcação.')
    },
    onSuccess: async () => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['progress'] }),
        qc.invalidateQueries({ queryKey: ['today'] }),
      ])
    },
  })
}

export function useStudySession(courseSlug: string, numero: number, enabled = true) {
  return useQuery({
    queryKey: ['study-session', courseSlug, numero],
    queryFn: async () => {
      const { data, response } = await api.GET(
        '/api/courses/{course_slug}/lessons/{number}/study-session',
        {
          params: { path: { course_slug: courseSlug, number: numero } },
        },
      )
      if (!data) {
        throw new Error(
          `A API respondeu ${response?.status ?? 'nada'} ao buscar a sessão de estudo.`,
        )
      }
      return data
    },
    enabled: enabled && Boolean(courseSlug),
    staleTime: 0,
  })
}

export function useSalvarStudySession(courseSlug: string, numero: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationKey: ['study-session', courseSlug, numero, 'save'],
    scope: { id: `study-session-${courseSlug}-${numero}` },
    mutationFn: async (body: StudySessionInput) => {
      const { data, response } = await api.PUT(
        '/api/courses/{course_slug}/lessons/{number}/study-session',
        {
          params: { path: { course_slug: courseSlug, number: numero } },
          body,
        },
      )
      if (!data) {
        throw new Error(
          `A API respondeu ${response?.status ?? 'nada'} ao salvar a sessão de estudo.`,
        )
      }
      return data
    },
    onSuccess: async (data) => {
      qc.setQueryData(['study-session', courseSlug, numero], data)
      await qc.invalidateQueries({ queryKey: ['today'] })
    },
  })
}
