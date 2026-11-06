import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import { ApiError } from './errors'
import { READ_POLICY } from './readPolicy'
import { invalidateStudy } from './invalidateStudy'
import type { components } from './schema'

export type ListeningResource = components['schemas']['ListeningResourceOut']
export type ListeningProgress = components['schemas']['ListeningProgressOut']
export type ListeningInput = components['schemas']['ListeningProgressIn']

export function useListeningConfig(userId: number) {
  return useQuery({
    queryKey: ['listening-config', userId], ...READ_POLICY,
    queryFn: async () => {
      const { data, response } = await api.GET('/api/listening/config')
      if (!data) throw new ApiError('a disponibilidade do listening', response)
      return data
    },
  })
}

export function useListeningCatalog(userId: number, enabled: boolean) {
  return useQuery({
    queryKey: ['listening-catalog', userId], enabled, ...READ_POLICY,
    queryFn: async () => {
      const { data, response } = await api.GET('/api/listening/resources')
      if (!data) throw new ApiError('as atividades de listening', response)
      return data
    },
  })
}

export function useListeningProgress(userId: number, enabled: boolean) {
  return useQuery({
    queryKey: ['listening-progress', userId], enabled, ...READ_POLICY, staleTime: 0,
    queryFn: async () => {
      const { data, response } = await api.GET('/api/me/listening/progress')
      if (!data) throw new ApiError('seu progresso de listening', response)
      return data
    },
  })
}

export function useMarkListening(userId: number, slug: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationKey: ['listening-mark', userId, slug],
    networkMode: 'always', retry: false,
    mutationFn: async (body: ListeningInput) => {
      const { data, response } = await api.PUT('/api/me/listening/progress/{slug}', {
        params: { path: { slug } }, body,
      })
      if (!data) throw new ApiError('a marcação de listening', response)
      return data
    },
    // Ler o estado atual também cobre repetição de um recibo antigo e conflito entre abas.
    onSettled: () => invalidateStudy(qc, 'listeningChange'),
  })
}
