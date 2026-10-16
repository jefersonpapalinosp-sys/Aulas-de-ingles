import { IDBObjectStore } from 'fake-indexeddb'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { setAccessToken, setSessionReadOnly, setSessionUser } from '../../api/session'
import {
  ATTEMPT_QUEUE_EVENT, ATTEMPT_QUEUE_STORAGE_KEY, LEGACY_ATTEMPT_QUEUE_STORAGE_KEY,
  discardBlockedAttempts, listQueuedAttempts, queueAttempt, syncAttemptQueue,
  type QueuedAttempt,
} from './attemptQueue'
import { attemptStore } from './attemptQueueStore'

vi.mock('../../api/client', () => ({ api: { POST: vi.fn() } }))
const { api } = await import('../../api/client')
const entry = (n: number, userId = 7): QueuedAttempt => ({
  userId, exerciseId: n + 1, answer: `answer-${n}`, idempotencyKey: `key-${n}`,
  createdAt: '2026-10-13T10:00:00Z', courseSlug: 'voa-level-2', lessonNumber: 6, sessionId: 44,
})

beforeEach(() => {
  localStorage.clear()
  vi.resetAllMocks()
  setAccessToken('test')
  setSessionUser(7)
  setSessionReadOnly(false)
})
afterEach(() => vi.restoreAllMocks())

describe('fila transacional v3', () => {
  it('preserva respostas 1–100 e recusa 101 explicitamente; limite é por aluno', async () => {
    await Promise.all(Array.from({ length: 100 }, (_, n) => queueAttempt(entry(n))))
    await expect(queueAttempt(entry(100))).rejects.toThrow('atingiu 100')
    const stored = await listQueuedAttempts(7)
    expect(stored).toHaveLength(100)
    expect(stored.map((item) => item.idempotencyKey).sort()).toEqual(Array.from({ length: 100 }, (_, n) => `key-${n}`).sort())
    await queueAttempt({ ...entry(0, 8), answer: 'resposta de outra conta' })
    expect(await listQueuedAttempts(8)).toEqual([{ ...entry(0, 8), answer: 'resposta de outra conta' }])
  })

  it('duas inserções concorrentes na última vaga não ultrapassam o limite', async () => {
    await Promise.all(Array.from({ length: 99 }, (_, n) => queueAttempt(entry(n))))
    const result = await Promise.allSettled([queueAttempt(entry(99)), queueAttempt(entry(100))])
    expect(result.filter((item) => item.status === 'fulfilled')).toHaveLength(1)
    expect(result.filter((item) => item.status === 'rejected')).toHaveLength(1)
    expect(await listQueuedAttempts(7)).toHaveLength(100)
  })

  it('duas gravações da mesma chave são idempotentes; payload diferente é erro', async () => {
    await Promise.all([queueAttempt(entry(1)), queueAttempt(entry(1))])
    expect(await listQueuedAttempts(7)).toHaveLength(1)
    await expect(queueAttempt({ ...entry(1), answer: 'outro texto' })).rejects.toThrow('Nenhuma foi sobrescrita')
    expect((await listQueuedAttempts(7))[0]?.answer).toBe('answer-1')
  })

  it('transação abortada após sucesso do request não publica gravação confirmada', async () => {
    const listener = vi.fn()
    window.addEventListener(ATTEMPT_QUEUE_EVENT, listener)
    const original = IDBObjectStore.prototype.add
    vi.spyOn(IDBObjectStore.prototype, 'add').mockImplementation(function (this: IDBObjectStore, ...args) {
      const request = original.apply(this, args)
      request.addEventListener('success', () => request.transaction!.abort())
      return request
    })
    await expect(queueAttempt(entry(1))).rejects.toThrow('Não foi possível gravar')
    expect(listener).not.toHaveBeenCalled()
    expect(await listQueuedAttempts(7)).toEqual([])
    window.removeEventListener(ATTEMPT_QUEUE_EVENT, listener)
  })

  it('quota e IndexedDB indisponível não removem respostas existentes', async () => {
    await queueAttempt(entry(1))
    const spy = vi.spyOn(IDBObjectStore.prototype, 'add').mockImplementation(() => { throw new DOMException('Full', 'QuotaExceededError') })
    await expect(queueAttempt(entry(2))).rejects.toThrow('armazenamento está cheio')
    spy.mockRestore()
    expect(await listQueuedAttempts(7)).toEqual([entry(1)])
    const db = indexedDB
    Object.defineProperty(globalThis, 'indexedDB', { configurable: true, value: undefined })
    await expect(queueAttempt(entry(2))).rejects.toThrow('Não foi possível gravar')
    Object.defineProperty(globalThis, 'indexedDB', { configurable: true, value: db })
    expect(await listQueuedAttempts(7)).toEqual([entry(1)])
  })

  it('falha de BroadcastChannel não transforma commit válido em falso erro', async () => {
    vi.stubGlobal('BroadcastChannel', class { constructor() { throw new Error('Blocked') } })
    await expect(queueAttempt(entry(1))).resolves.toBeUndefined()
    expect(await listQueuedAttempts(7)).toEqual([entry(1)])
    vi.unstubAllGlobals()
  })
})

describe('migração recuperável v1/v2', () => {
  it('preserva união, contexto v2, bloqueios, contas e mais de 100 itens importados', async () => {
    const legacy = Array.from({ length: 101 }, (_, n) => entry(n))
    const blocked = { ...entry(0), syncFailure: { status: 409, failedAt: '2026-10-13T10:00:00Z' } }
    const v1 = JSON.stringify(legacy.map((item) => ({ userId: item.userId, exerciseId: item.exerciseId,
      answer: item.answer, idempotencyKey: item.idempotencyKey, createdAt: item.createdAt })))
    const v2 = JSON.stringify({ version: 2, attempts: [blocked, entry(0, 8)] })
    localStorage.setItem(LEGACY_ATTEMPT_QUEUE_STORAGE_KEY, v1)
    localStorage.setItem(ATTEMPT_QUEUE_STORAGE_KEY, v2)
    const stored = await listQueuedAttempts(7)
    expect(stored).toHaveLength(101)
    expect(stored.find((item) => item.idempotencyKey === 'key-0')).toEqual(blocked)
    expect(await listQueuedAttempts(8)).toEqual([entry(0, 8)])
    await expect(queueAttempt(entry(102))).rejects.toThrow('atingiu 100')
    expect(localStorage.getItem(LEGACY_ATTEMPT_QUEUE_STORAGE_KEY)).toBe(v1)
    expect(localStorage.getItem(ATTEMPT_QUEUE_STORAGE_KEY)).toBe(v2)
  })

  it('migração com falha é atômica e conserva a fonte original', async () => {
    const raw = JSON.stringify([entry(1), entry(2)])
    localStorage.setItem(LEGACY_ATTEMPT_QUEUE_STORAGE_KEY, raw)
    const original = IDBObjectStore.prototype.put
    const spy = vi.spyOn(IDBObjectStore.prototype, 'put').mockImplementation(function (this: IDBObjectStore, ...args) {
      if (this.name === 'attempts' && (args[0] as QueuedAttempt).exerciseId === 3) throw new DOMException('Full', 'QuotaExceededError')
      return original.apply(this, args)
    })
    await expect(listQueuedAttempts(7)).rejects.toThrow('armazenamento está cheio')
    expect(localStorage.getItem(LEGACY_ATTEMPT_QUEUE_STORAGE_KEY)).toBe(raw)
    spy.mockRestore()
    localStorage.removeItem(LEGACY_ATTEMPT_QUEUE_STORAGE_KEY) // apenas fixture em memória
    expect(await listQueuedAttempts(7)).toEqual([])
    localStorage.setItem(LEGACY_ATTEMPT_QUEUE_STORAGE_KEY, raw)
    expect(await listQueuedAttempts(7)).toEqual([entry(1), entry(2)])
  })

  it.each(['{inválido', '{"version":9,"attempts":[]}', JSON.stringify({ version: 2, attempts: [entry(1), { userId: 7 }] })])('não interpreta fonte corrompida como fila vazia: %s', async (raw) => {
    localStorage.setItem(ATTEMPT_QUEUE_STORAGE_KEY, raw)
    await expect(listQueuedAttempts(7)).rejects.toThrow(/preservada/)
    expect(localStorage.getItem(ATTEMPT_QUEUE_STORAGE_KEY)).toBe(raw)
  })

  it('detecta colisão entre fontes sem sobrescrever ou importar parcialmente', async () => {
    localStorage.setItem(LEGACY_ATTEMPT_QUEUE_STORAGE_KEY, JSON.stringify([entry(1)]))
    localStorage.setItem(ATTEMPT_QUEUE_STORAGE_KEY, JSON.stringify({ version: 2, attempts: [{ ...entry(1), answer: 'diferente' }] }))
    await expect(listQueuedAttempts(7)).rejects.toThrow('mesma chave')
    localStorage.clear()
    expect(await listQueuedAttempts(7)).toEqual([])
  })

  it('novas escritas de aba antiga são importadas sem ressuscitar itens finalizados', async () => {
    localStorage.setItem(LEGACY_ATTEMPT_QUEUE_STORAGE_KEY, JSON.stringify([entry(1)]))
    expect(await listQueuedAttempts(7)).toEqual([entry(1)])
    await attemptStore.finish(7, 'key-1')
    localStorage.setItem(LEGACY_ATTEMPT_QUEUE_STORAGE_KEY, JSON.stringify([entry(1), entry(2)]))
    expect(await listQueuedAttempts(7)).toEqual([entry(2)])
    await attemptStore.block(7, 'key-2', 409)
    await discardBlockedAttempts(7, ['key-2'])
    localStorage.setItem(LEGACY_ATTEMPT_QUEUE_STORAGE_KEY, JSON.stringify([entry(1), entry(2), entry(3)]))
    expect(await listQueuedAttempts(7)).toEqual([entry(3)])
  })

  it('exclui uma conta das filas e impede que fontes legadas a restaurem', async () => {
    const deleted = entry(1, 91)
    const preserved = entry(1, 92)
    localStorage.setItem(LEGACY_ATTEMPT_QUEUE_STORAGE_KEY, JSON.stringify([deleted, preserved]))
    expect(await listQueuedAttempts(91)).toEqual([deleted])
    await attemptStore.deleteUser(91)
    expect(await listQueuedAttempts(91)).toEqual([])
    expect(await listQueuedAttempts(92)).toEqual([preserved])
    expect(JSON.parse(localStorage.getItem(LEGACY_ATTEMPT_QUEUE_STORAGE_KEY)!)).toEqual([
      preserved,
    ])
    localStorage.setItem(
      LEGACY_ATTEMPT_QUEUE_STORAGE_KEY,
      JSON.stringify([deleted, preserved, entry(2, 92)]),
    )
    expect(await listQueuedAttempts(91)).toEqual([])
    await expect(queueAttempt(entry(3, 91))).rejects.toThrow('já foram removidos')
  })
})

describe('sincronização exclusiva e recuperação', () => {
  it('serializa rodadas concorrentes e envia cada chave uma única vez', async () => {
    await Promise.all([queueAttempt(entry(1)), queueAttempt(entry(2))])
    vi.mocked(api.POST).mockResolvedValue({ data: { attempt_id: 1, correct: true }, response: new Response() } as never)
    const result = await Promise.all([syncAttemptQueue(7), syncAttemptQueue(7)])
    expect(result.reduce((total, item) => total + item.synced, 0)).toBe(2)
    expect(api.POST).toHaveBeenCalledTimes(2)
    expect(await listQueuedAttempts(7)).toEqual([])
  })

  it('commit remoto seguido de falha local conserva a chave para reconciliação', async () => {
    await queueAttempt(entry(1))
    vi.mocked(api.POST).mockResolvedValue({ data: { attempt_id: 1, correct: true }, response: new Response() } as never)
    const spy = vi.spyOn(attemptStore, 'finish').mockRejectedValueOnce(new Error('Falha no commit local'))
    await expect(syncAttemptQueue(7)).rejects.toThrow('Falha no commit local')
    expect(await listQueuedAttempts(7)).toEqual([entry(1)])
    spy.mockRestore()
    expect((await syncAttemptQueue(7)).synced).toBe(1)
    expect(api.POST).toHaveBeenCalledTimes(2)
    expect(vi.mocked(api.POST).mock.calls[0]?.[1]).toEqual(vi.mocked(api.POST).mock.calls[1]?.[1])
    expect(await listQueuedAttempts(7)).toEqual([])
  })

  it('sem Web Locks mantém a persistência, mas recusa sincronização insegura', async () => {
    Object.defineProperty(navigator, 'locks', { configurable: true, value: undefined })
    await queueAttempt(entry(1))
    await expect(syncAttemptQueue(7)).rejects.toThrow('Web Locks')
    expect(await listQueuedAttempts(7)).toEqual([entry(1)])
    expect(api.POST).not.toHaveBeenCalled()
  })

  it('HTTP 200 sem confirmação válida não remove a resposta', async () => {
    await queueAttempt(entry(1))
    vi.mocked(api.POST).mockResolvedValueOnce({ data: {}, response: new Response() } as never)
    await expect(syncAttemptQueue(7)).rejects.toThrow('resultado válido')
    expect(await listQueuedAttempts(7)).toEqual([entry(1)])
  })

  it('remoção confirmada alcança somente bloqueadas selecionadas da conta atual', async () => {
    await Promise.all([queueAttempt(entry(1)), queueAttempt(entry(2)), queueAttempt(entry(3)), queueAttempt(entry(1, 8))])
    await attemptStore.block(7, 'key-1', 409)
    await attemptStore.block(7, 'key-2', 422)
    await attemptStore.block(8, 'key-1', 409)
    await discardBlockedAttempts(7, ['key-1', 'key-3'])
    expect((await listQueuedAttempts(7)).map((item) => item.idempotencyKey)).toEqual(['key-2', 'key-3'])
    expect(await listQueuedAttempts(8)).toHaveLength(1)
  })
})
