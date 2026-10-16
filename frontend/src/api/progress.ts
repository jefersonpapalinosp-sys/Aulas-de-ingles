import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type StudySession, type StudySessionInput } from './client'
import { invalidateStudy } from './invalidateStudy'
import { ApiError } from './errors'

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
        qc.invalidateQueries({ queryKey: ['course-completion', courseSlug] }),
      ])
    },
  })
}

export function useStudySession(courseSlug: string, numero: number, enabled = true) {
  return useQuery({
    queryKey: ['study-session', courseSlug, numero],
    // Permite falhar offline e hidratar o progresso local, sem ficar pausado para sempre.
    networkMode: 'always', retry: false,
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
      const current = qc.getQueryData<StudySession>(['study-session', courseSlug, numero])
      // Executado dentro do scope serial; lê a revisão da confirmação anterior.
      const payload = { ...body, expected_revision: current?.revision ?? 0,
        completed_steps: [...new Set([...(current?.completed_steps ?? []), ...body.completed_steps])] }
      const { data, response } = await api.PUT(
        '/api/courses/{course_slug}/lessons/{number}/study-session',
        {
          params: { path: { course_slug: courseSlug, number: numero } },
          body: payload,
        },
      )
      if (!data) {
        throw new ApiError('a sessão de estudo', response)
      }
      return data
    },
    onSuccess: async (data) => {
      qc.setQueryData(['study-session', courseSlug, numero], data)
      await invalidateStudy(qc)
    },
    onError: () => qc.invalidateQueries({ queryKey: ['study-session', courseSlug, numero] }),
  })
}
