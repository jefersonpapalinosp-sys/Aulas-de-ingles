import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ReviewItemType } from './client'
import { api } from './client'

export type ReviewFilters = {
  itemType?: ReviewItemType
  skill?: string
  maxMinutes?: number
}

export function useDeckSummary() {
  return useQuery({
    queryKey: ['review', 'summary'],
    queryFn: async () => {
      const { data, response } = await api.GET('/api/review/summary')
      if (!data) throw new Error(`A API respondeu ${response?.status ?? 'nada'} ao buscar o deck.`)
      return data
    },
  })
}

export function useDueCards(filters: ReviewFilters = {}) {
  return useQuery({
    queryKey: ['review', 'due', filters],
    queryFn: async () => {
      const { data, response } = await api.GET('/api/review/due', {
        params: {
          query: {
            limit: 20,
            item_type: filters.itemType,
            skill: filters.skill,
            max_minutes: filters.maxMinutes,
          },
        },
      })
      if (!data) throw new Error(`A API respondeu ${response?.status ?? 'nada'} ao buscar cartas.`)
      return data
    },
    staleTime: 0,
  })
}

export function useSuspendedReviewItems() {
  return useQuery({
    queryKey: ['review', 'items', 'suspended'],
    queryFn: async () => {
      const { data, response } = await api.GET('/api/review/items', {
        params: { query: { status: 'suspended' } },
      })
      if (!data) {
        throw new Error(`A API respondeu ${response?.status ?? 'nada'} ao buscar suspensos.`)
      }
      return data
    },
  })
}

export function useAvaliar() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ cardId, quality }: { cardId: number; quality: number }) => {
      const { data, response } = await api.POST('/api/review/{item_id}/grade', {
        params: { path: { item_id: cardId } },
        body: { quality },
      })
      if (!data) throw new Error(`A API respondeu ${response?.status ?? 'nada'} ao avaliar.`)
      return data
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['review'] })
      void qc.invalidateQueries({ queryKey: ['progress'] })
    },
  })
}

export function useSetReviewItemStatus() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ itemId, status }: { itemId: number; status: 'active' | 'suspended' }) => {
      const { data, response } = await api.PATCH('/api/review/{item_id}', {
        params: { path: { item_id: itemId } },
        body: { status },
      })
      if (!data) throw new Error(`A API respondeu ${response?.status ?? 'nada'} ao alterar.`)
      return data
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['review'] })
      void qc.invalidateQueries({ queryKey: ['progress'] })
      void qc.invalidateQueries({ queryKey: ['today'] })
    },
  })
}

export function useDeleteReviewItem() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (itemId: number) => {
      const { response } = await api.DELETE('/api/review/{item_id}', {
        params: { path: { item_id: itemId } },
      })
      if (!response?.ok) throw new Error('Não foi possível excluir o item.')
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['review'] })
      void qc.invalidateQueries({ queryKey: ['progress'] })
      void qc.invalidateQueries({ queryKey: ['today'] })
    },
  })
}

export function useAdicionarItem() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vocabItemId: number) => {
      const { data, response } = await api.POST('/api/review/items/{vocab_item_id}', {
        params: { path: { vocab_item_id: vocabItemId } },
      })
      if (!data) throw new Error(`A API respondeu ${response?.status ?? 'nada'} ao adicionar.`)
      return data
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['review'] })
      void qc.invalidateQueries({ queryKey: ['progress'] })
    },
  })
}
