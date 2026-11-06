import { useEffect, useMemo, useSyncExternalStore } from 'react'
import { api } from './client'
import { PositionConflict, PositionSync } from '../features/media/positionSync'
import { nativeAllowed } from '../features/listening/nativeQueue'
import { useSessao } from './auth'

export function useNativePosition(userId: number, sessionId: number, version: number) {
  const { offline } = useSessao()
  const controller = useMemo(() => {
    async function read() {
      if (!nativeAllowed(userId)) throw new Error('session_unconfirmed')
      const { data } = await api.GET('/api/listening/sessions/{session_id}/position', { params: { path: { session_id: sessionId } } })
      if (!data) throw new Error('position_unavailable')
      return { ...data, media_id: data.session_id }
    }
    return new PositionSync(userId, sessionId, { allowed: () => nativeAllowed(userId), read,
      save: async body => {
        if (!nativeAllowed(userId)) throw new Error('session_unconfirmed')
        const { data, response } = await api.PUT('/api/listening/sessions/{session_id}/position', {
          params: { path: { session_id: sessionId } }, body,
        })
        if (response.status === 409) throw new PositionConflict(await read())
        if (!data) throw new Error('position_unavailable')
        return { ...data, media_id: data.session_id }
      },
    }, `native-${version}`)
  }, [userId, sessionId, version])
  const state = useSyncExternalStore(controller.subscribe, controller.snapshot)
  useEffect(() => {
    controller.activate()
    const sync = () => { void controller.sync() }
    sync()
    window.addEventListener('online', sync); window.addEventListener('focus', sync); window.addEventListener('storage', sync)
    return () => { controller.dispose(); window.removeEventListener('online', sync); window.removeEventListener('focus', sync); window.removeEventListener('storage', sync) }
  }, [controller])
  useEffect(() => { if (!offline) void controller.sync() }, [controller, offline])
  return { ...state, record: controller.record, retry: controller.sync, resolve: controller.resolve, snapshot: controller.snapshot }
}
