import { useCallback, useEffect, useState } from 'react'
import {
  listPendingAttempts,
  subscribeAttemptQueue,
  type AttemptQueueChangeEventDetail,
  type AttemptQueueSyncEventDetail,
} from '../offline/attemptQueue'
import type { PracticeSession } from './types'

/** Quais exercícios desta sessão têm resposta esperando na fila offline.
 *
 * O conjunto existe para bloquear o card: enquanto a tentativa não foi
 * corrigida pela conta, uma segunda resposta ao mesmo item seria uma tentativa
 * duplicada. Por isso o card segue bloqueado durante o sync e só é liberado
 * quando o GET da sessão confirma a correção.
 */
export function useQueuedAttempts(
  session: PracticeSession | null,
  userId: number,
  reload: () => Promise<unknown>,
) {
  const [queued, setQueued] = useState<Set<number>>(() => new Set())
  const [error, setError] = useState('')

  useEffect(() => {
    if (!session) return
    let alive = true
    let revision = 0
    const refresh = async (event?: Event) => {
      const current = ++revision
      const reason = (event as CustomEvent<AttemptQueueChangeEventDetail> | undefined)?.detail?.reason
      // Durante o sync não há releitura: o card continua "Na fila" até a sessão
      // confirmar, para não abrir janela para uma segunda tentativa.
      if (reason === 'synced' || reason === 'blocked') return
      try {
        if (reason === 'external') await reload()
        const pending = await listPendingAttempts(userId)
        if (!alive || current !== revision) return
        setQueued(new Set(pending
          .filter((attempt) => attempt.sessionId === session.id)
          .map((attempt) => attempt.exerciseId)))
      } catch (failure) {
        if (alive) setError(failure instanceof Error ? failure.message : 'Não foi possível consultar as respostas locais.')
      }
    }
    void refresh()
    const unsubscribe = subscribeAttemptQueue((event) => { void refresh(event) })
    return () => { alive = false; unsubscribe() }
  }, [reload, session, userId])

  useEffect(() => {
    function handleSync(event: Event) {
      const detail = (event as CustomEvent<AttemptQueueSyncEventDetail>).detail
      if (!session || detail.userId !== userId) return
      const synced = detail.syncedAttempts.filter((attempt) => attempt.sessionId === session.id)
      const rejected = detail.rejectedAttempts.filter((attempt) => attempt.sessionId === session.id)
      if (synced.length === 0 && rejected.length === 0) return

      void reload().then(() => {
        setQueued((current) => {
          const next = new Set(current)
          synced.forEach((attempt) => next.delete(attempt.exerciseId))
          rejected.forEach((attempt) => next.delete(attempt.exerciseId))
          return next
        })
      }).catch(() => setError('Não foi possível confirmar o resultado sincronizado. Tente retomar a sessão.'))
    }
    return subscribeAttemptQueue(() => undefined, handleSync)
  }, [reload, session, userId])

  const mark = useCallback((exerciseId: number) => {
    setQueued((current) => new Set(current).add(exerciseId))
  }, [])
  const forget = useCallback(() => { setQueued(new Set()) }, [])

  return { queued, error, mark, forget, clearError: useCallback(() => setError(''), []) }
}
