import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'

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

export function useDueCards() {
  return useQuery({
    queryKey: ['review', 'due'],
    queryFn: async () => {
      const { data, response } = await api.GET('/api/review/due', {
        params: { query: { limit: 20 } },
      })
      if (!data) throw new Error(`A API respondeu ${response?.status ?? 'nada'} ao buscar cartas.`)
      return data
    },
    staleTime: 0,
  })
}

export function useAvaliar() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ cardId, quality }: { cardId: number; quality: number }) => {
      const { data, response } = await api.POST('/api/review/{card_id}/grade', {
        params: { path: { card_id: cardId } },
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
