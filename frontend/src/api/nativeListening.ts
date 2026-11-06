import { useQuery } from '@tanstack/react-query'
import { api } from './client'
import { ApiError } from './errors'
import { READ_POLICY } from './readPolicy'
import type { components } from './schema'

export type NativeActivity = components['schemas']['NativeActivityOut']
export type NativeSession = components['schemas']['NativeSessionOut']
export type NativeResponse = components['schemas']['NativeResponseIn']

export function useNativeCatalog(userId: number) {
  const config = useQuery({ queryKey: ['native-listening-config', userId], ...READ_POLICY,
    queryFn: async () => {
      const { data, response } = await api.GET('/api/listening/native-config')
      if (!data) throw new ApiError('a disponibilidade da prática nativa', response)
      return data
    },
  })
  return useQuery({ queryKey: ['native-listening-catalog', userId], ...READ_POLICY,
    enabled: config.data?.enabled === true,
    queryFn: async () => {
      const { data, response } = await api.GET('/api/listening/native')
      if (!data) throw new ApiError('as práticas nativas', response)
      return data
    },
  })
}

export async function startNative(slug: string, version: number, operation_key: string) {
  const { data, response } = await api.POST('/api/listening/native/{slug}/sessions', {
    params: { path: { slug } }, body: { version, operation_key },
  })
  if (!data) throw new ApiError('o início da prática', response)
  return data
}

export async function respondNative(session_id: number, body: NativeResponse) {
  const { data, response } = await api.POST('/api/listening/sessions/{session_id}/responses', {
    params: { path: { session_id } }, body,
  })
  if (!data) throw new ApiError('a resposta de listening', response)
  return data
}
