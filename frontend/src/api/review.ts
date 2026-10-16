import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ReviewItemType } from './client'
import { api } from './client'
import { ApiError } from './errors'
import { invalidateStudy } from './invalidateStudy'

export type ReviewGradeCommand = {
  cardId: number
  quality: number
  idempotencyKey: string
  expectedRevision: number
}

export type ReviewFilters = {
  courseSlug?: string
  unitSlug?: string
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
            course: filters.courseSlug,
            unit: filters.unitSlug,
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

export function useSuspendedReviewItems(
  filters: Pick<ReviewFilters, 'courseSlug' | 'unitSlug'> = {},
  cursor?: string,
) {
  return useQuery({
    queryKey: ['review', 'suspended', filters, cursor],
    queryFn: async () => {
      const { data, response } = await api.GET('/api/review/items/page', {
        params: {
          query: {
            course: filters.courseSlug,
            unit: filters.unitSlug,
            cursor,
          },
        },
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
    mutationFn: async ({ cardId, quality, idempotencyKey, expectedRevision }: ReviewGradeCommand) => {
      const { data, response } = await api.POST('/api/review/{item_id}/grade', {
        params: { path: { item_id: cardId } },
        body: { quality, idempotency_key: idempotencyKey, expected_revision: expectedRevision },
      })
      if (!data) throw new ApiError('o resultado da revisão', response)
      return data
    },
    onSuccess: () => invalidateStudy(qc),
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
