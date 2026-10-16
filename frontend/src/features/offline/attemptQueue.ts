import { api } from '../../api/client'
import { sessionSnapshot } from '../../api/session'
import type { components } from '../../api/schema'
import { attemptStore, QueueStorageError, ATTEMPT_QUEUE_STORAGE_KEY, LEGACY_ATTEMPT_QUEUE_STORAGE_KEY } from './attemptQueueStore'
export { ATTEMPT_QUEUE_STORAGE_KEY, LEGACY_ATTEMPT_QUEUE_STORAGE_KEY, MAX_ATTEMPTS_PER_USER, QueueStorageError } from './attemptQueueStore'

export const ATTEMPT_QUEUE_EVENT = 'aulas:attempt-queue-change'
export const ATTEMPT_QUEUE_SYNC_EVENT = 'aulas:attempt-queue-sync'

export type AttemptQueueChangeReason = 'queued' | 'synced' | 'blocked' | 'discarded' | 'external'

export type AttemptQueueChangeEventDetail = {
  reason: AttemptQueueChangeReason
}

export type QueuedAttempt = {
  userId: number
  exerciseId: number
  answer: string
  idempotencyKey: string
  createdAt: string
  sessionId?: number
  courseSlug?: string
  lessonNumber?: number
  syncFailure?: AttemptSyncFailure
}

export type AttemptSyncFailure = {
  status: number
  failedAt: string
}

export type SyncedQueuedAttempt = {
  exerciseId: number
  idempotencyKey: string
  attemptId: number
  correct: boolean
  sessionId?: number
  courseSlug?: string
  lessonNumber?: number
}

export type RejectedQueuedAttempt = {
  exerciseId: number
  idempotencyKey: string
  status: number
  sessionId?: number
  courseSlug?: string
  lessonNumber?: number
}

export type AttemptQueueSyncResult = {
  synced: number
  pending: number
  blocked: number
  syncedAttempts: SyncedQueuedAttempt[]
  rejectedAttempts: RejectedQueuedAttempt[]
}

export type AttemptQueueSyncEventDetail = AttemptQueueSyncResult & {
  userId: number
}

type AttemptRequestBody = components['schemas']['AttemptIn'] & {
  practice_session_id?: number
}

export type QueueStats = { pending: number; blocked: number; total: number }

function publish(kind: 'change' | 'sync', detail: AttemptQueueChangeEventDetail | AttemptQueueSyncEventDetail): void {
  window.dispatchEvent(new CustomEvent(kind === 'change' ? ATTEMPT_QUEUE_EVENT : ATTEMPT_QUEUE_SYNC_EVENT, { detail }))
  try {
    if (typeof BroadcastChannel === 'undefined') return
    const channel = new BroadcastChannel('aulas:attempt-queue:v3')
    channel.postMessage({ kind, detail })
    channel.close()
  } catch { /* Notificação é opcional; o commit IDB já foi confirmado. */ }
}

/** Eventos entre abas não carregam respostas, textos nem credenciais. O foco
 * relê o banco também quando BroadcastChannel não estiver disponível. */
export function subscribeAttemptQueue(
  change: (event: Event) => void,
  sync?: (event: Event) => void,
): () => void {
  let channel: BroadcastChannel | null = null
  try { if (typeof BroadcastChannel !== 'undefined') channel = new BroadcastChannel('aulas:attempt-queue:v3') } catch { /* Foco relê a fila. */ }
  if (channel) channel.onmessage = ({ data }: MessageEvent) => {
    if (data?.kind === 'change') change(new CustomEvent(ATTEMPT_QUEUE_EVENT, { detail: data.detail }))
    if (data?.kind === 'sync') sync?.(new CustomEvent(ATTEMPT_QUEUE_SYNC_EVENT, { detail: data.detail }))
  }
  const refresh = () => change(new CustomEvent(ATTEMPT_QUEUE_EVENT, { detail: { reason: 'external' } }))
  const legacyChanged = (event: StorageEvent) => {
    if (event.key === ATTEMPT_QUEUE_STORAGE_KEY || event.key === LEGACY_ATTEMPT_QUEUE_STORAGE_KEY) refresh()
  }
  window.addEventListener(ATTEMPT_QUEUE_EVENT, change)
  if (sync) window.addEventListener(ATTEMPT_QUEUE_SYNC_EVENT, sync)
  window.addEventListener('focus', refresh)
  window.addEventListener('storage', legacyChanged)
  return () => {
    channel?.close()
    window.removeEventListener(ATTEMPT_QUEUE_EVENT, change)
    if (sync) window.removeEventListener(ATTEMPT_QUEUE_SYNC_EVENT, sync)
    window.removeEventListener('focus', refresh)
    window.removeEventListener('storage', legacyChanged)
  }
}

export function listQueuedAttempts(userId: number): Promise<QueuedAttempt[]> {
  return attemptStore.list(userId)
}

export async function listPendingAttempts(userId: number): Promise<QueuedAttempt[]> {
  return (await listQueuedAttempts(userId)).filter((attempt) => attempt.syncFailure === undefined)
}

export async function getAttemptQueueStats(userId: number): Promise<QueueStats> {
  const attempts = await listQueuedAttempts(userId)
  const blocked = attempts.filter((attempt) => attempt.syncFailure !== undefined).length
  return { pending: attempts.length - blocked, blocked, total: attempts.length }
}

export async function queueAttempt(attempt: QueuedAttempt): Promise<void> {
  if (await attemptStore.add(attempt)) publish('change', { reason: 'queued' })
}

export async function discardBlockedAttempts(userId: number, keys?: string[]): Promise<void> {
  await attemptStore.discardBlocked(userId, keys)
  publish('change', { reason: 'discarded' })
}

export async function deleteAttemptQueueForUser(userId: number): Promise<void> {
  await attemptStore.deleteUser(userId)
  publish('change', { reason: 'discarded' })
}

/** Locks são por origem/usuário e liberados pelo navegador se a aba fechar.
 * Sem suporte, falhar explicitamente; nunca fingir exclusão mútua com um flag. */
export async function syncAttemptQueue(userId: number): Promise<AttemptQueueSyncResult> {
  if (!navigator.locks) throw new QueueStorageError('Este navegador não oferece sincronização segura entre abas. As respostas continuam na fila; use um navegador com Web Locks em HTTPS ou localhost.')
  const inicio = sessionSnapshot().geracao
  return navigator.locks.request(`aulas:attempt-queue:sync:${userId}`, { mode: 'exclusive' },
    () => synchronize(userId, inicio))
}

function isPermanentClientError(status: number): boolean {
  return (
    status >= 400 &&
    status < 500 &&
    status !== 401 &&
    status !== 403 &&
    status !== 408 &&
    status !== 425 &&
    status !== 429
  )
}

async function synchronize(userId: number, inicio: number): Promise<AttemptQueueSyncResult> {
  const syncedAttempts: SyncedQueuedAttempt[] = []
  const rejectedAttempts: RejectedQueuedAttempt[] = []
  const mesmaSessao = () => {
    const atual = sessionSnapshot()
    return atual.geracao === inicio && atual.usuarioId === userId && !atual.perfilNaoConfirmado
  }
  let failure: unknown
  try {
    for (const attempt of await listPendingAttempts(userId)) {
      // A fila pertence ao aluno, não ao token disponível quando uma Promise
      // antiga retoma. Logout/troca de conta interrompem também os próximos itens.
      if (!mesmaSessao()) break
      const body: AttemptRequestBody = {
        answer: attempt.answer,
        idempotency_key: attempt.idempotencyKey,
        ...(attempt.sessionId === undefined ? {} : { practice_session_id: attempt.sessionId }),
      }
      let result
      try {
        result = await api.POST('/api/exercises/{exercise_id}/attempt', {
          params: { path: { exercise_id: attempt.exerciseId } },
          body,
        })
      } catch (error) {
        if (
          error instanceof TypeError ||
          (error instanceof DOMException && ['NetworkError', 'AbortError'].includes(error.name))
        ) {
          break
        }
        throw error
      }
      if (!mesmaSessao()) break
      const { data, response } = result

      if (!data) {
        // Falhas permanentes ficam preservadas como bloqueadas, mas não impedem
        // as tentativas seguintes. Isso é essencial quando uma sessão ficou
        // incompatível após uma atualização de conteúdo. Rede, autenticação,
        // limite e erros 5xx continuam interrompendo a rodada para tentar depois.
        if (response && isPermanentClientError(response.status)) {
          await attemptStore.block(userId, attempt.idempotencyKey, response.status)
          publish('change', { reason: 'blocked' })
          rejectedAttempts.push({
            exerciseId: attempt.exerciseId,
            idempotencyKey: attempt.idempotencyKey,
            status: response.status,
            ...(attempt.sessionId === undefined ? {} : { sessionId: attempt.sessionId }),
            ...(attempt.courseSlug === undefined ? {} : { courseSlug: attempt.courseSlug }),
            ...(attempt.lessonNumber === undefined ? {} : { lessonNumber: attempt.lessonNumber }),
          })
          continue
        }
        break
      }
      if (!Number.isInteger(data.attempt_id) || data.attempt_id <= 0 || typeof data.correct !== 'boolean') {
        throw new QueueStorageError('A API não confirmou a tentativa com um resultado válido. A resposta continua na fila.')
      }

      await attemptStore.finish(userId, attempt.idempotencyKey)
      publish('change', { reason: 'synced' })
      syncedAttempts.push({
        exerciseId: attempt.exerciseId,
        idempotencyKey: attempt.idempotencyKey,
        attemptId: data.attempt_id,
        correct: data.correct,
        ...(attempt.sessionId === undefined ? {} : { sessionId: attempt.sessionId }),
        ...(attempt.courseSlug === undefined ? {} : { courseSlug: attempt.courseSlug }),
        ...(attempt.lessonNumber === undefined ? {} : { lessonNumber: attempt.lessonNumber }),
      })
    }

  } catch (error) { failure = error }

  const stats = await getAttemptQueueStats(userId)
  const result: AttemptQueueSyncResult = {
    synced: syncedAttempts.length,
    pending: stats.pending,
    blocked: stats.blocked,
    syncedAttempts,
    rejectedAttempts,
  }
  publish('sync', { userId, ...result })
  if (failure) throw failure
  return result
}
