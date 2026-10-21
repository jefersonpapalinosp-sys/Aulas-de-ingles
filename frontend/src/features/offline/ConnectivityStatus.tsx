import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { invalidateStudy } from '../../api/invalidateStudy'
import { practicePath } from '../../routing/courseRoutes'
import {
  discardBlockedAttempts, listQueuedAttempts, subscribeAttemptQueue, syncAttemptQueue,
  type AttemptQueueSyncEventDetail, type QueuedAttempt,
} from './attemptQueue'

type InstallPromptEvent = Event & {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

function failureReason(status: number): string {
  if (status === 409) return 'O conteúdo ou a sessão mudou. Reabra a aula e refaça esta resposta.'
  if (status === 404 || status === 410) return 'A atividade não está mais disponível.'
  if (status === 422 || status === 400) return 'A resposta não é compatível com o formato atual da atividade.'
  return 'A API recusou esta tentativa. A resposta foi preservada para consulta.'
}

export function ConnectivityStatus({ userId, offlineSession }: { userId: number; offlineSession: boolean }) {
  const qc = useQueryClient()
  const [online, setOnline] = useState(() => navigator.onLine)
  const [attempts, setAttempts] = useState<QueuedAttempt[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [syncing, setSyncing] = useState(false)
  const syncingRef = useRef(false)
  const alive = useRef(false)
  const revision = useRef(0)
  const [message, setMessage] = useState('')
  const [discarding, setDiscarding] = useState(false)
  const [confirmation, setConfirmation] = useState<string[] | null>(null)
  const [installPrompt, setInstallPrompt] = useState<InstallPromptEvent | null>(null)
  const blocked = attempts.filter((item) => item.syncFailure)
  const pending = attempts.length - blocked.length

  const refreshPending = useCallback(async () => {
    const current = ++revision.current
    try {
      const items = await listQueuedAttempts(userId)
      if (alive.current && current === revision.current) {
        setAttempts(items)
        setError('')
      }
    } catch (err) {
      if (alive.current && current === revision.current) {
        setError(err instanceof Error ? err.message : 'Não foi possível consultar a fila local.')
      }
    } finally {
      if (alive.current && current === revision.current) setLoading(false)
    }
  }, [userId])

  const sync = useCallback(async () => {
    if (!navigator.onLine || offlineSession || syncingRef.current) return
    syncingRef.current = true
    setSyncing(true)
    setMessage('')
    try {
      const result = await syncAttemptQueue(userId)
      if (!alive.current) return
      await refreshPending()
      if (result.synced > 0) {
        setMessage(`${result.synced} tentativa(s) sincronizada(s).`)
      } else if (result.pending > 0) {
        setMessage('A sincronização não foi concluída. As respostas continuam na fila.')
      }
    } catch (err) {
      if (alive.current) setError(err instanceof Error ? err.message : 'Não foi possível sincronizar agora. A fila foi preservada.')
    } finally {
      syncingRef.current = false
      if (alive.current) setSyncing(false)
    }
  }, [offlineSession, refreshPending, userId])

  useEffect(() => {
    alive.current = true
    void refreshPending()
    const handleOnline = () => setOnline(true)
    const handleOffline = () => setOnline(false)
    const handleInstall = (event: Event) => {
      event.preventDefault()
      setInstallPrompt(event as InstallPromptEvent)
    }
    const unsubscribe = subscribeAttemptQueue(() => { void refreshPending() }, (event) => {
      const detail = (event as CustomEvent<AttemptQueueSyncEventDetail>).detail
      if (detail.userId !== userId) return
      void refreshPending()
      if (detail.synced > 0) void invalidateStudy(qc, 'queueSync').catch(() => {
        if (alive.current) setMessage('A resposta foi sincronizada. Atualize a página para consultar o progresso.')
      })
    })
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    window.addEventListener('beforeinstallprompt', handleInstall)
    return () => {
      alive.current = false
      revision.current += 1
      unsubscribe()
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
      window.removeEventListener('beforeinstallprompt', handleInstall)
    }
  }, [refreshPending, qc, userId])

  useEffect(() => {
    if (online && !offlineSession && pending > 0) void sync()
  }, [online, offlineSession, pending, sync])

  if (online && !loading && attempts.length === 0 && !message && !error && !installPrompt) return null

  return (
    <aside className={`connectivity queue-status ${online ? 'online' : 'offline'}`} aria-label="Fila de respostas">
      <p role="status" aria-live="polite">
        {loading ? 'Consultando fila local…' : error ? 'A fila precisa de atenção.' : `${pending} pendente(s) · ${blocked.length} bloqueada(s).`}
        {!online ? ' Você está offline.' : offlineSession ? ' Sincronização pausada até confirmar a sessão.' : ''}
        {message && ` ${message}`}
      </p>
      {error && <p role="alert">{error}</p>}
      {error && <button type="button" onClick={() => void refreshPending()}>Consultar fila novamente</button>}
      {online && !offlineSession && pending > 0 && (
        <button type="button" onClick={() => void sync()} disabled={syncing}>
          {syncing ? 'Sincronizando…' : 'Sincronizar agora'}
        </button>
      )}
      {attempts.length > 0 && <details>
        <summary>Consultar respostas preservadas</summary>
        <ul>
          {attempts.map((item) => <li key={item.idempotencyKey}>
            <strong>{item.lessonNumber ? `Aula ${item.lessonNumber} · ` : ''}Exercício {item.exerciseId}</strong>
            <p>{item.syncFailure ? `${failureReason(item.syncFailure.status)} (HTTP ${item.syncFailure.status})` : 'Aguardando sincronização.'}</p>
            <pre>{item.answer}</pre>
            {item.courseSlug && item.lessonNumber && (
              <Link to={practicePath(item.courseSlug, item.lessonNumber)}>Abrir exercícios da aula</Link>
            )}
          </li>)}
        </ul>
      </details>}
      {blocked.length > 0 && !confirmation && (
        <button type="button" onClick={() => setConfirmation(blocked.map((item) => item.idempotencyKey))}>Descartar incompatíveis…</button>
      )}
      {confirmation && <div>
        <p>Remover {confirmation.length} resposta(s) bloqueada(s) desta fila? Copie o texto antes; esta remoção não pode ser desfeita pela interface. Pendências não serão apagadas.</p>
        <button type="button" disabled={discarding} onClick={() => {
          setDiscarding(true)
          void discardBlockedAttempts(userId, confirmation).then(async () => {
            if (!alive.current) return
            setConfirmation(null)
            setMessage('Respostas selecionadas removidas da fila. Os dados da conta não foram alterados.')
            await refreshPending()
          }).catch((err: unknown) => {
            if (alive.current) setError(err instanceof Error ? err.message : 'Não foi possível remover. As respostas foram preservadas.')
          }).finally(() => { if (alive.current) setDiscarding(false) })
        }}>Confirmar remoção</button>
        <button type="button" disabled={discarding} onClick={() => setConfirmation(null)}>Cancelar</button>
      </div>}
      {installPrompt && <button type="button" onClick={() => {
        void installPrompt.prompt().then(() => installPrompt.userChoice).then(() => setInstallPrompt(null))
          .catch(() => setMessage('Não foi possível instalar o aplicativo agora.'))
      }}>Instalar aplicativo</button>}
    </aside>
  )
}
