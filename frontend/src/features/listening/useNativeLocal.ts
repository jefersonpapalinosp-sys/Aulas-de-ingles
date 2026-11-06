import { useCallback, useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { invalidateStudy } from '../../api/invalidateStudy'
import { nativeAllowed, syncNative } from './nativeQueue'
import { NATIVE_EVENT, nativeStore, type NativeLocal } from './nativeStore'

export function useNativeLocal(userId: number, online: boolean, offline: boolean) {
  const [local, setLocal] = useState<NativeLocal | null>(null)
  const [error, setError] = useState('')
  const [syncing, setSyncing] = useState(false)
  const client = useQueryClient()
  const sync = useCallback(async () => {
    if (!nativeAllowed(userId)) return
    setSyncing(true); setError('')
    try { await syncNative(userId); await invalidateStudy(client, 'nativeListeningChange') }
    catch { setError('Envio não confirmado. As respostas salvas permanecem pendentes neste dispositivo.') }
    finally { setSyncing(false) }
  }, [userId, client])
  useEffect(() => {
    let active = true
    let request = 0
    const refresh = () => {
      const latest = ++request
      void nativeStore.read(userId).then(value => { if (active && latest === request) setLocal(value) })
        .catch(() => { if (active) setError('Não foi possível ler os dados locais. Não limpe o armazenamento; tente novamente.') })
    }
    const listener = (event: Event) => { if ((event as CustomEvent<number>).detail === userId) refresh() }
    const channel = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel(NATIVE_EVENT) : null
    if (channel) channel.onmessage = (event: MessageEvent<unknown>) => { if (event.data === userId) refresh() }
    refresh()
    window.addEventListener(NATIVE_EVENT, listener); window.addEventListener('focus', refresh)
    return () => { active = false; channel?.close(); window.removeEventListener(NATIVE_EVENT, listener); window.removeEventListener('focus', refresh) }
  }, [userId])
  useEffect(() => { if (online && !offline) void sync() }, [online, offline, sync])
  return { local, error, setError, syncing, sync }
}
