import { useEffect, useMemo, useSyncExternalStore } from 'react'
import { PositionConflict, PositionSync } from '../features/media/positionSync'
import { api } from './client'
import { sessionSnapshot } from './session'

export function canSyncFor(userId: number) {
  const session = sessionSnapshot()
  return navigator.onLine && session.usuarioId === userId && !!session.token && !session.perfilNaoConfirmado
}

export function useMediaPositionSync(mediaId: number, userId: number) {
  const controller = useMemo(() => {
    async function read() {
      if (!canSyncFor(userId)) throw new Error('session_unconfirmed')
      const { data } = await api.GET('/api/media/{media_id}/position', {
        params: { path: { media_id: mediaId } },
      })
      if (!data) throw new Error('media_read_failed')
      return data
    }
    return new PositionSync(userId, mediaId, {
      allowed: () => canSyncFor(userId), read,
      save: async (body) => {
        if (!canSyncFor(userId)) throw new Error('session_unconfirmed')
        const { data, response } = await api.PUT('/api/media/{media_id}/position', {
          params: { path: { media_id: mediaId } }, body,
        })
        if (response.status === 409) throw new PositionConflict(await read())
        if (!data) throw new Error('media_save_failed')
        return data
      },
    })
  }, [mediaId, userId])
  const state = useSyncExternalStore(controller.subscribe, controller.snapshot)
  useEffect(() => {
    controller.activate()
    void controller.sync()
    const sync = () => { void controller.sync() }
    const storage = (event: StorageEvent) => {
      if (event.key === null || event.key.startsWith(controller.prefix)) sync()
    }
    window.addEventListener('online', sync)
    window.addEventListener('focus', sync)
    window.addEventListener('storage', storage)
    return () => {
      controller.dispose()
      window.removeEventListener('online', sync)
      window.removeEventListener('focus', sync)
      window.removeEventListener('storage', storage)
    }
  }, [controller])
  return { ...state, record: (position: number) => controller.record(position),
    finish: () => controller.record(0, true), retry: controller.sync,
    resolve: controller.resolve, snapshot: controller.snapshot }
}
