import { api } from '../../api/client'
import type { components } from '../../api/schema'

export const ATTEMPT_QUEUE_EVENT = 'aulas:attempt-queue-change'
export const ATTEMPT_QUEUE_SYNC_EVENT = 'aulas:attempt-queue-sync'
export const ATTEMPT_QUEUE_STORAGE_KEY = 'aulas:offline-attempts:v2'
export const LEGACY_ATTEMPT_QUEUE_STORAGE_KEY = 'aulas:offline-attempts:v1'
const MAX_ATTEMPTS = 100

export type AttemptQueueChangeReason = 'queued' | 'synced' | 'blocked' | 'discarded'

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

type AttemptQueueStorageV2 = {
  version: 2
  attempts: QueuedAttempt[]
}

type AttemptRequestBody = components['schemas']['AttemptIn'] & {
  practice_session_id?: number
}

function optionalPositiveInteger(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isInteger(value) && value > 0 ? value : undefined
}

function optionalNonEmptyString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim().length > 0 ? value : undefined
}

function parseSyncFailure(value: unknown): AttemptSyncFailure | undefined {
  if (
    typeof value !== 'object' ||
    value === null ||
    typeof Reflect.get(value, 'status') !== 'number' ||
    !Number.isInteger(Reflect.get(value, 'status')) ||
    typeof Reflect.get(value, 'failedAt') !== 'string'
  ) {
    return undefined
  }
  return {
    status: Reflect.get(value, 'status') as number,
    failedAt: Reflect.get(value, 'failedAt') as string,
  }
}

function parseAttempt(item: unknown): QueuedAttempt | null {
  if (
    typeof item !== 'object' ||
    item === null ||
    typeof Reflect.get(item, 'userId') !== 'number' ||
    typeof Reflect.get(item, 'exerciseId') !== 'number' ||
    typeof Reflect.get(item, 'answer') !== 'string' ||
    typeof Reflect.get(item, 'idempotencyKey') !== 'string' ||
    typeof Reflect.get(item, 'createdAt') !== 'string'
  ) {
    return null
  }

  const attempt: QueuedAttempt = {
    userId: Reflect.get(item, 'userId') as number,
    exerciseId: Reflect.get(item, 'exerciseId') as number,
    answer: Reflect.get(item, 'answer') as string,
    idempotencyKey: Reflect.get(item, 'idempotencyKey') as string,
    createdAt: Reflect.get(item, 'createdAt') as string,
  }
  const sessionId = optionalPositiveInteger(Reflect.get(item, 'sessionId'))
  const courseSlug = optionalNonEmptyString(Reflect.get(item, 'courseSlug'))
  const lessonNumber = optionalPositiveInteger(Reflect.get(item, 'lessonNumber'))
  const syncFailure = parseSyncFailure(Reflect.get(item, 'syncFailure'))

  if (sessionId !== undefined) attempt.sessionId = sessionId
  if (courseSlug !== undefined) attempt.courseSlug = courseSlug
  if (lessonNumber !== undefined) attempt.lessonNumber = lessonNumber
  if (syncFailure !== undefined) attempt.syncFailure = syncFailure
  return attempt
}

function parseAttempts(raw: string | null, version: 1 | 2): QueuedAttempt[] {
  if (raw === null) return []
  try {
    const parsed: unknown = JSON.parse(raw)
    const items =
      version === 2 &&
      typeof parsed === 'object' &&
      parsed !== null &&
      Reflect.get(parsed, 'version') === 2 &&
      Array.isArray(Reflect.get(parsed, 'attempts'))
        ? (Reflect.get(parsed, 'attempts') as unknown[])
        : version === 1 && Array.isArray(parsed)
          ? parsed
          : []
    return items.flatMap((item) => {
      const attempt = parseAttempt(item)
      return attempt ? [attempt] : []
    })
  } catch {
    return []
  }
}

function mergeAttempts(legacy: QueuedAttempt[], current: QueuedAttempt[]): QueuedAttempt[] {
  const merged = [...legacy]
  const indexes = new Map(merged.map((attempt, index) => [attempt.idempotencyKey, index]))

  for (const attempt of current) {
    const previousIndex = indexes.get(attempt.idempotencyKey)
    if (previousIndex === undefined) {
      indexes.set(attempt.idempotencyKey, merged.length)
      merged.push(attempt)
    } else {
      // A versão v2 pode conter o contexto de sessão que não existia na v1.
      merged[previousIndex] = attempt
    }
  }
  return merged.slice(-MAX_ATTEMPTS)
}

function persistV2(attempts: QueuedAttempt[]): void {
  const storage: AttemptQueueStorageV2 = {
    version: 2,
    attempts: attempts.slice(-MAX_ATTEMPTS),
  }
  localStorage.setItem(ATTEMPT_QUEUE_STORAGE_KEY, JSON.stringify(storage))
}

function readAll(): QueuedAttempt[] {
  const current = parseAttempts(localStorage.getItem(ATTEMPT_QUEUE_STORAGE_KEY), 2)
  const legacyRaw = localStorage.getItem(LEGACY_ATTEMPT_QUEUE_STORAGE_KEY)
  if (legacyRaw === null) return current

  const merged = mergeAttempts(parseAttempts(legacyRaw, 1), current)
  try {
    persistV2(merged)
    // A chave antiga só sai depois que a gravação v2 foi confirmada pelo browser.
    localStorage.removeItem(LEGACY_ATTEMPT_QUEUE_STORAGE_KEY)
  } catch {
    // A leitura continua disponível mesmo se a quota ou o modo privado impedir a migração.
  }
  return merged
}

function writeAll(attempts: QueuedAttempt[], reason: AttemptQueueChangeReason): void {
  persistV2(attempts)
  localStorage.removeItem(LEGACY_ATTEMPT_QUEUE_STORAGE_KEY)
  window.dispatchEvent(
    new CustomEvent<AttemptQueueChangeEventDetail>(ATTEMPT_QUEUE_EVENT, {
      detail: { reason },
    }),
  )
}

export function listQueuedAttempts(userId: number): QueuedAttempt[] {
  return readAll().filter((attempt) => attempt.userId === userId)
}

export function listPendingAttempts(userId: number): QueuedAttempt[] {
  return listQueuedAttempts(userId).filter((attempt) => attempt.syncFailure === undefined)
}

export function getAttemptQueueStats(userId: number): {
  pending: number
  blocked: number
  total: number
} {
  const attempts = listQueuedAttempts(userId)
  const blocked = attempts.filter((attempt) => attempt.syncFailure !== undefined).length
  return { pending: attempts.length - blocked, blocked, total: attempts.length }
}

export function queueAttempt(attempt: QueuedAttempt): void {
  const attempts = readAll()
  if (attempts.some((item) => item.idempotencyKey === attempt.idempotencyKey)) return
  writeAll([...attempts, attempt], 'queued')
}

function removeAttempt(idempotencyKey: string): void {
  writeAll(readAll().filter((attempt) => attempt.idempotencyKey !== idempotencyKey), 'synced')
}

function blockAttempt(idempotencyKey: string, status: number): void {
  writeAll(
    readAll().map((attempt) =>
      attempt.idempotencyKey === idempotencyKey
        ? { ...attempt, syncFailure: { status, failedAt: new Date().toISOString() } }
        : attempt,
    ),
    'blocked',
  )
}

export function discardBlockedAttempts(userId: number): void {
  writeAll(
    readAll().filter(
      (attempt) => attempt.userId !== userId || attempt.syncFailure === undefined,
    ),
    'discarded',
  )
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

export async function syncAttemptQueue(userId: number): Promise<AttemptQueueSyncResult> {
  const syncedAttempts: SyncedQueuedAttempt[] = []
  const rejectedAttempts: RejectedQueuedAttempt[] = []
  for (const attempt of listPendingAttempts(userId)) {
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
        (error instanceof DOMException && error.name === 'NetworkError')
      ) {
        break
      }
      throw error
    }
    const { data, response } = result

    if (!data) {
      // Falhas permanentes ficam preservadas como bloqueadas, mas não impedem
      // as tentativas seguintes. Isso é essencial quando uma sessão ficou
      // incompatível após uma atualização de conteúdo. Rede, autenticação,
      // limite e erros 5xx continuam interrompendo a rodada para tentar depois.
      if (response && isPermanentClientError(response.status)) {
        blockAttempt(attempt.idempotencyKey, response.status)
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

    removeAttempt(attempt.idempotencyKey)
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

  const stats = getAttemptQueueStats(userId)
  const result: AttemptQueueSyncResult = {
    synced: syncedAttempts.length,
    pending: stats.pending,
    blocked: stats.blocked,
    syncedAttempts,
    rejectedAttempts,
  }
  window.dispatchEvent(
    new CustomEvent<AttemptQueueSyncEventDetail>(ATTEMPT_QUEUE_SYNC_EVENT, {
      detail: { userId, ...result },
    }),
  )
  return result
}
