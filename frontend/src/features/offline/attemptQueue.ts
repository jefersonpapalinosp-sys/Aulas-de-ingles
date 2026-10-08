import { api } from '../../api/client'

export const ATTEMPT_QUEUE_EVENT = 'aulas:attempt-queue-change'
const STORAGE_KEY = 'aulas:offline-attempts:v1'
const MAX_ATTEMPTS = 100

export type QueuedAttempt = {
  userId: number
  exerciseId: number
  answer: string
  idempotencyKey: string
  createdAt: string
}

function readAll(): QueuedAttempt[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]')
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      (item): item is QueuedAttempt =>
        typeof item === 'object' &&
        item !== null &&
        typeof item.userId === 'number' &&
        typeof item.exerciseId === 'number' &&
        typeof item.answer === 'string' &&
        typeof item.idempotencyKey === 'string' &&
        typeof item.createdAt === 'string',
    )
  } catch {
    return []
  }
}

function writeAll(attempts: QueuedAttempt[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(attempts.slice(-MAX_ATTEMPTS)))
  window.dispatchEvent(new Event(ATTEMPT_QUEUE_EVENT))
}

export function listQueuedAttempts(userId: number): QueuedAttempt[] {
  return readAll().filter((attempt) => attempt.userId === userId)
}

export function queueAttempt(attempt: QueuedAttempt): void {
  const attempts = readAll()
  if (attempts.some((item) => item.idempotencyKey === attempt.idempotencyKey)) return
  writeAll([...attempts, attempt])
}

function removeAttempt(idempotencyKey: string): void {
  writeAll(readAll().filter((attempt) => attempt.idempotencyKey !== idempotencyKey))
}

export async function syncAttemptQueue(userId: number): Promise<{
  synced: number
  pending: number
}> {
  let synced = 0
  for (const attempt of listQueuedAttempts(userId)) {
    const { data, response } = await api.POST('/api/exercises/{exercise_id}/attempt', {
      params: { path: { exercise_id: attempt.exerciseId } },
      body: { answer: attempt.answer, idempotency_key: attempt.idempotencyKey },
    })

    if (!data) {
      // Sem resposta significa conexão interrompida. 401/403 aguardam a sessão
      // ser renovada; outros erros permanecem na fila para não perder estudo.
      if (!response || response.status === 401 || response.status === 403) break
      break
    }

    removeAttempt(attempt.idempotencyKey)
    synced += 1
  }

  return { synced, pending: listQueuedAttempts(userId).length }
}
