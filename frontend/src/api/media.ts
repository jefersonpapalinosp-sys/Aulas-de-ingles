import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'

function mediaPositionKey(userId: number, mediaId: number) {
  return ['media-position', userId, mediaId] as const
}

export function useMediaPosition(mediaId: number, userId: number) {
  return useQuery({
    queryKey: mediaPositionKey(userId, mediaId),
    queryFn: async () => {
      const { data, response } = await api.GET('/api/media/{media_id}/position', {
        params: { path: { media_id: mediaId } },
      })
      if (!data) {
        throw new Error(
          `A API respondeu ${response?.status ?? 'nada'} ao buscar a posição da mídia.`,
        )
      }
      return data
    },
    enabled: userId > 0,
    staleTime: 0,
    retry: false,
  })
}

export function useSaveMediaPosition(mediaId: number, userId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    scope: { id: `media-position-${mediaId}` },
    mutationFn: async (positionSeconds: number) => {
      const { data, response } = await api.PUT('/api/media/{media_id}/position', {
        params: { path: { media_id: mediaId } },
        body: { position_seconds: positionSeconds },
      })
      if (!data) {
        throw new Error(
          `A API respondeu ${response?.status ?? 'nada'} ao salvar a posição da mídia.`,
        )
      }
      return data
    },
    onSuccess: (data) => queryClient.setQueryData(mediaPositionKey(userId, mediaId), data),
  })
}

export function useClearMediaPosition(mediaId: number, userId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { response } = await api.DELETE('/api/media/{media_id}/position', {
        params: { path: { media_id: mediaId } },
      })
      if (!response?.ok) throw new Error('Não foi possível limpar a posição da mídia.')
    },
    onSuccess: () => {
      queryClient.setQueryData(mediaPositionKey(userId, mediaId), {
        media_id: mediaId,
        position_seconds: 0,
        updated_at: null,
      })
    },
  })
}
