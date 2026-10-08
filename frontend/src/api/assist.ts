import { useQuery } from '@tanstack/react-query'
import { api } from './client'

export function useAssistStatus(userId: number) {
  return useQuery({
    queryKey: ['assist-status', userId],
    queryFn: async () => {
      const { data } = await api.GET('/api/assist/status')
      if (!data) throw new Error('Não foi possível consultar os recursos experimentais.')
      return data
    },
    staleTime: 60_000,
    retry: false,
  })
}
