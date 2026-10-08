import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type StudySessionInput } from './client'

export function useProgress() {
  return useQuery({
    queryKey: ['progress'],
    queryFn: async () => {
      const { data, response } = await api.GET('/api/me/progress')
      if (!data) throw new Error(`A API respondeu ${response?.status ?? 'nada'} ao buscar progresso.`)
      return data
    },
    staleTime: 0,
  })
}

/** Marca ou desmarca uma aula; a lista de progresso é invalidada em seguida. */
export function useMarcarEstudada() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ numero, estudada }: { numero: number; estudada: boolean }) => {
      const op = estudada ? api.PUT : api.DELETE
      const { response } = await op('/api/lessons/{number}/studied', {
        params: { path: { number: numero } },
      })
      if (!response?.ok) throw new Error('Não foi possível salvar a marcação.')
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['progress'] }),
  })
}

export function useStudySession(numero: number, enabled = true) {
  return useQuery({
    queryKey: ['study-session', numero],
    queryFn: async () => {
      const { data, response } = await api.GET('/api/lessons/{number}/study-session', {
        params: { path: { number: numero } },
      })
      if (!data) {
        throw new Error(
          `A API respondeu ${response?.status ?? 'nada'} ao buscar a sessão de estudo.`,
        )
      }
      return data
    },
    enabled,
    staleTime: 0,
  })
}

export function useSalvarStudySession(numero: number) {
  const qc = useQueryClient()
  return useMutation({
    scope: { id: `study-session-${numero}` },
    mutationFn: async (body: StudySessionInput) => {
      const { data, response } = await api.PUT('/api/lessons/{number}/study-session', {
        params: { path: { number: numero } },
        body,
      })
      if (!data) {
        throw new Error(
          `A API respondeu ${response?.status ?? 'nada'} ao salvar a sessão de estudo.`,
        )
      }
      return data
    },
    onSuccess: (data) => qc.setQueryData(['study-session', numero], data),
  })
}
