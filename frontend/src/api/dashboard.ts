import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type StudyPlanInput } from './client'

export function useToday() {
  return useQuery({
    queryKey: ['today'],
    queryFn: async () => {
      const { data, response } = await api.GET('/api/me/today')
      if (!data) throw new Error(`A API respondeu ${response?.status ?? 'nada'} ao abrir Hoje.`)
      return data
    },
  })
}

export function useSkills() {
  return useQuery({
    queryKey: ['skills'],
    queryFn: async () => {
      const { data, response } = await api.GET('/api/me/skills')
      if (!data) {
        throw new Error(`A API respondeu ${response?.status ?? 'nada'} ao buscar competências.`)
      }
      return data
    },
  })
}

export function useSaveStudyPlan() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: StudyPlanInput) => {
      const { data, response } = await api.PUT('/api/me/study-plan', { body })
      if (!data) throw new Error(`A API respondeu ${response?.status ?? 'nada'} ao salvar o plano.`)
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['today'] })
    },
  })
}
