import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ATTEMPT_QUEUE_EVENT,
  listQueuedAttempts,
  syncAttemptQueue,
} from './attemptQueue'

type InstallPromptEvent = Event & {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

export function ConnectivityStatus({
  userId,
  offlineSession,
}: {
  userId: number
  offlineSession: boolean
}) {
  const qc = useQueryClient()
  const [online, setOnline] = useState(() => navigator.onLine)
  const [pending, setPending] = useState(() => listQueuedAttempts(userId).length)
  const [syncing, setSyncing] = useState(false)
  const syncingRef = useRef(false)
  const [message, setMessage] = useState('')
  const [installPrompt, setInstallPrompt] = useState<InstallPromptEvent | null>(null)

  const refreshPending = useCallback(
    () => setPending(listQueuedAttempts(userId).length),
    [userId],
  )

  const sync = useCallback(async () => {
    if (!navigator.onLine || offlineSession || syncingRef.current) return
    syncingRef.current = true
    setSyncing(true)
    setMessage('')
    try {
      const result = await syncAttemptQueue(userId)
      setPending(result.pending)
      if (result.synced > 0) {
        setMessage(
          result.synced === 1
            ? '1 tentativa foi sincronizada.'
            : `${result.synced} tentativas foram sincronizadas.`,
        )
        await Promise.all([
          qc.invalidateQueries({ queryKey: ['progress'] }),
          qc.invalidateQueries({ queryKey: ['review'] }),
          qc.invalidateQueries({ queryKey: ['skills'] }),
          qc.invalidateQueries({ queryKey: ['today'] }),
        ])
      }
    } finally {
      syncingRef.current = false
      setSyncing(false)
    }
  }, [offlineSession, qc, userId])

  useEffect(() => {
    const handleOnline = () => setOnline(true)
    const handleOffline = () => setOnline(false)
    const handleInstall = (event: Event) => {
      event.preventDefault()
      setInstallPrompt(event as InstallPromptEvent)
    }
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    window.addEventListener(ATTEMPT_QUEUE_EVENT, refreshPending)
    window.addEventListener('beforeinstallprompt', handleInstall)
    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
      window.removeEventListener(ATTEMPT_QUEUE_EVENT, refreshPending)
      window.removeEventListener('beforeinstallprompt', handleInstall)
    }
  }, [refreshPending])

  useEffect(() => {
    if (online && !offlineSession && pending > 0) void sync()
  }, [online, offlineSession, pending, sync])

  if (online && pending === 0 && !message && !installPrompt) return null

  return (
    <div className={`connectivity ${online ? 'online' : 'offline'}`} role="status" aria-live="polite">
      <span>
        {!online || offlineSession
          ? `Você está offline${pending ? ` · ${pending} tentativa${pending === 1 ? '' : 's'} na fila` : ''}.`
          : message || `${pending} tentativa${pending === 1 ? '' : 's'} aguardando sincronização.`}
      </span>
      {online && !offlineSession && pending > 0 && (
        <button type="button" onClick={() => void sync()} disabled={syncing}>
          {syncing ? 'Sincronizando…' : 'Sincronizar agora'}
        </button>
      )}
      {installPrompt && (
        <button
          type="button"
          onClick={() => {
            void installPrompt.prompt().then(() => installPrompt.userChoice).then(() => {
              setInstallPrompt(null)
            })
          }}
        >
          Instalar aplicativo
        </button>
      )}
    </div>
  )
}
