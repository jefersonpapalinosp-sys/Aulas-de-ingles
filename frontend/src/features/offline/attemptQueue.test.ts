import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ATTEMPT_QUEUE_EVENT,
  ATTEMPT_QUEUE_STORAGE_KEY,
  ATTEMPT_QUEUE_SYNC_EVENT,
  LEGACY_ATTEMPT_QUEUE_STORAGE_KEY,
  discardBlockedAttempts,
  getAttemptQueueStats,
  listQueuedAttempts,
  queueAttempt,
  syncAttemptQueue,
  type AttemptQueueSyncEventDetail,
} from './attemptQueue'

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

  it('migra a fila v1 sem perder tentativas ou idempotência', () => {
    localStorage.setItem(LEGACY_ATTEMPT_QUEUE_STORAGE_KEY, JSON.stringify([attempt]))

    expect(listQueuedAttempts(7)).toEqual([attempt])
    expect(localStorage.getItem(LEGACY_ATTEMPT_QUEUE_STORAGE_KEY)).toBeNull()
    expect(JSON.parse(localStorage.getItem(ATTEMPT_QUEUE_STORAGE_KEY) ?? '')).toEqual({
      version: 2,
      attempts: [attempt],
    })

    queueAttempt(attempt)
    expect(listQueuedAttempts(7)).toEqual([attempt])
  })

  it('preserva o contexto da prática na fila v2 e o envia para a API', async () => {
    const contextualAttempt = {
      ...attempt,
      sessionId: 91,
      courseSlug: 'voa-level-1',
      lessonNumber: 31,
    }
    queueAttempt(contextualAttempt)
    vi.mocked(api.POST).mockResolvedValue({
      data: { attempt_id: 401, correct: true },
      response: new Response(),
    } as never)

    await expect(syncAttemptQueue(7)).resolves.toEqual({
      synced: 1,
      pending: 0,
      blocked: 0,
      syncedAttempts: [
        {
          exerciseId: 31,
          idempotencyKey: 'offline-1',
          attemptId: 401,
          correct: true,
          sessionId: 91,
          courseSlug: 'voa-level-1',
          lessonNumber: 31,
        },
      ],
      rejectedAttempts: [],
    })
    expect(api.POST).toHaveBeenCalledWith('/api/exercises/{exercise_id}/attempt', {
      params: { path: { exercise_id: 31 } },
      body: {
        answer: 'faster',
        idempotency_key: 'offline-1',
        practice_session_id: 91,
      },
    })
  })

  it('reutiliza a chave original, emite reconciliação e remove somente após confirmação', async () => {
    const listener = vi.fn<(detail: AttemptQueueSyncEventDetail) => void>()
    const handleSync: EventListener = (event) =>
      listener((event as CustomEvent<AttemptQueueSyncEventDetail>).detail)
    window.addEventListener(ATTEMPT_QUEUE_SYNC_EVENT, handleSync)
    queueAttempt(attempt)
    vi.mocked(api.POST).mockResolvedValue({
      data: { attempt_id: 402, correct: false },
      response: new Response(),
    } as never)

    await expect(syncAttemptQueue(7)).resolves.toEqual({
      synced: 1,
      pending: 0,
      blocked: 0,
      syncedAttempts: [
        {
          exerciseId: 31,
          idempotencyKey: 'offline-1',
          attemptId: 402,
          correct: false,
        },
      ],
      rejectedAttempts: [],
    })
    expect(api.POST).toHaveBeenCalledWith('/api/exercises/{exercise_id}/attempt', {
      params: { path: { exercise_id: 31 } },
      body: { answer: 'faster', idempotency_key: 'offline-1' },
    })
    expect(listener).toHaveBeenCalledTimes(1)
    expect(listener.mock.calls[0]?.[0]).toEqual({
      userId: 7,
      synced: 1,
      pending: 0,
      blocked: 0,
      syncedAttempts: [
        {
          exerciseId: 31,
          idempotencyKey: 'offline-1',
          attemptId: 402,
          correct: false,
        },
      ],
      rejectedAttempts: [],
    })
    window.removeEventListener(ATTEMPT_QUEUE_SYNC_EVENT, handleSync)
  })

  it('mantém a tentativa quando a rede continua indisponível', async () => {
    queueAttempt(attempt)
    vi.mocked(api.POST).mockResolvedValue({ data: undefined, response: undefined } as never)

    await expect(syncAttemptQueue(7)).resolves.toEqual({
      synced: 0,
      pending: 1,
      blocked: 0,
      syncedAttempts: [],
      rejectedAttempts: [],
    })
    expect(listQueuedAttempts(7)).toEqual([attempt])
  })

  it('mantém a tentativa quando o fetch rejeita durante a sincronização', async () => {
    queueAttempt(attempt)
    vi.mocked(api.POST).mockRejectedValueOnce(new TypeError('Failed to fetch'))

    await expect(syncAttemptQueue(7)).resolves.toEqual({
      synced: 0,
      pending: 1,
      blocked: 0,
      syncedAttempts: [],
      rejectedAttempts: [],
    })
    expect(listQueuedAttempts(7)).toEqual([attempt])
  })

  it('isola uma tentativa incompatível e sincroniza as seguintes sem perder a resposta', async () => {
    const staleAttempt = {
      ...attempt,
      sessionId: 91,
      courseSlug: 'voa-level-1',
      lessonNumber: 31,
    }
    const nextAttempt = {
      ...attempt,
      exerciseId: 32,
      answer: 'next answer',
      idempotencyKey: 'offline-2',
      sessionId: 92,
    }
    queueAttempt(staleAttempt)
    queueAttempt(nextAttempt)
    vi.mocked(api.POST)
      .mockResolvedValueOnce({
        data: undefined,
        response: new Response(null, { status: 409 }),
      } as never)
      .mockResolvedValueOnce({
        data: { attempt_id: 403, correct: true },
        response: new Response(),
      } as never)

    const result = await syncAttemptQueue(7)

    expect(api.POST).toHaveBeenCalledTimes(2)
    expect(result).toMatchObject({
      synced: 1,
      pending: 0,
      blocked: 1,
      rejectedAttempts: [
        {
          exerciseId: 31,
          idempotencyKey: 'offline-1',
          status: 409,
          sessionId: 91,
          courseSlug: 'voa-level-1',
          lessonNumber: 31,
        },
      ],
    })
    expect(listQueuedAttempts(7)).toEqual([
      expect.objectContaining({
        ...staleAttempt,
        syncFailure: expect.objectContaining({ status: 409 }),
      }),
    ])
    expect(getAttemptQueueStats(7)).toEqual({ pending: 0, blocked: 1, total: 1 })

    vi.mocked(api.POST).mockClear()
    await expect(syncAttemptQueue(7)).resolves.toMatchObject({
      synced: 0,
      pending: 0,
      blocked: 1,
    })
    expect(api.POST).not.toHaveBeenCalled()

    discardBlockedAttempts(7)
    expect(listQueuedAttempts(7)).toEqual([])
  })
})
