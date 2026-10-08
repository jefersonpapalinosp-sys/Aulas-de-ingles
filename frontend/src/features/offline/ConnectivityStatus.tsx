import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ATTEMPT_QUEUE_EVENT,
  discardBlockedAttempts,
  getAttemptQueueStats,
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
  const [queue, setQueue] = useState(() => getAttemptQueueStats(userId))
  const [syncing, setSyncing] = useState(false)
  const syncingRef = useRef(false)
  const [message, setMessage] = useState('')
  const [installPrompt, setInstallPrompt] = useState<InstallPromptEvent | null>(null)

  const refreshPending = useCallback(
    () => setQueue(getAttemptQueueStats(userId)),
    [userId],
  )

  const sync = useCallback(async () => {
    if (!navigator.onLine || offlineSession || syncingRef.current) return
    syncingRef.current = true
    setSyncing(true)
    setMessage('')
    try {
      const result = await syncAttemptQueue(userId)
      setQueue({
        pending: result.pending,
        blocked: result.blocked,
        total: result.pending + result.blocked,
      })
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
          qc.invalidateQueries({ queryKey: ['practice-session'] }),
          qc.invalidateQueries({ queryKey: ['practice-session-active'] }),
        ])
      } else if (result.rejectedAttempts.length > 0) {
        setMessage('Uma tentativa antiga ficou incompatível com o conteúdo atual.')
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
    if (online && !offlineSession && queue.pending > 0) void sync()
  }, [online, offlineSession, queue.pending, sync])

  if (online && queue.total === 0 && !message && !installPrompt) return null

  const queueMessage =
    !online || offlineSession
      ? `Você está offline${queue.total ? ` · ${queue.total} tentativa${queue.total === 1 ? '' : 's'} na fila` : ''}.`
      : queue.blocked > 0
        ? `${message ? `${message} ` : ''}${queue.blocked} tentativa${queue.blocked === 1 ? '' : 's'} precisa${queue.blocked === 1 ? '' : 'm'} ser refeita${queue.blocked === 1 ? '' : 's'} após a atualização.${queue.pending > 0 ? ` ${queue.pending} ainda aguarda${queue.pending === 1 ? '' : 'm'} sincronização.` : ''}`
        : message ||
          `${queue.pending} tentativa${queue.pending === 1 ? '' : 's'} aguardando sincronização.`

  return (
    <div className={`connectivity ${online ? 'online' : 'offline'}`} role="status" aria-live="polite">
      <span>{queueMessage}</span>
      {online && !offlineSession && queue.pending > 0 && (
        <button type="button" onClick={() => void sync()} disabled={syncing}>
          {syncing ? 'Sincronizando…' : 'Sincronizar agora'}
        </button>
      )}
      {queue.blocked > 0 && (
        <button
          type="button"
          onClick={() => {
            discardBlockedAttempts(userId)
            setMessage('Tentativas incompatíveis removidas deste dispositivo.')
          }}
        >
          Descartar incompatíveis
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
