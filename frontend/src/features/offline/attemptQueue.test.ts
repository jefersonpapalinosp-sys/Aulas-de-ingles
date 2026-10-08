import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ATTEMPT_QUEUE_EVENT, listQueuedAttempts, queueAttempt, syncAttemptQueue } from './attemptQueue'

vi.mock('../../api/client', () => ({ api: { POST: vi.fn() } }))
const { api } = await import('../../api/client')

const attempt = {
  userId: 7,
  exerciseId: 31,
  answer: 'faster',
  idempotencyKey: 'offline-1',
  createdAt: '2026-10-07T12:00:00.000Z',
}

beforeEach(() => {
  localStorage.clear()
  vi.resetAllMocks()
})

describe('fila offline de tentativas', () => {
  it('separa a fila por aluno e não duplica a mesma chave idempotente', () => {
    const listener = vi.fn()
    window.addEventListener(ATTEMPT_QUEUE_EVENT, listener)
    queueAttempt(attempt)
    queueAttempt(attempt)
    queueAttempt({ ...attempt, userId: 8, idempotencyKey: 'offline-2' })

    expect(listQueuedAttempts(7)).toEqual([attempt])
    expect(listQueuedAttempts(8)).toHaveLength(1)
    expect(listener).toHaveBeenCalledTimes(2)
    window.removeEventListener(ATTEMPT_QUEUE_EVENT, listener)
  })

  it('reutiliza a chave original e remove somente depois da confirmação', async () => {
    queueAttempt(attempt)
    vi.mocked(api.POST).mockResolvedValue({ data: { correct: true }, response: new Response() } as never)

    await expect(syncAttemptQueue(7)).resolves.toEqual({ synced: 1, pending: 0 })
    expect(api.POST).toHaveBeenCalledWith('/api/exercises/{exercise_id}/attempt', {
      params: { path: { exercise_id: 31 } },
      body: { answer: 'faster', idempotency_key: 'offline-1' },
    })
  })

  it('mantém a tentativa quando a rede continua indisponível', async () => {
    queueAttempt(attempt)
    vi.mocked(api.POST).mockResolvedValue({ data: undefined, response: undefined } as never)

    await expect(syncAttemptQueue(7)).resolves.toEqual({ synced: 0, pending: 1 })
    expect(listQueuedAttempts(7)).toEqual([attempt])
  })
})
