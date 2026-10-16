import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from './client'

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
