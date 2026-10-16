import type { QueuedAttempt } from './attemptQueue'
import { readLocal, removeLocal, writeLocal } from '../../storage/local'

export const ATTEMPT_QUEUE_DB = 'aulas:offline-attempts:v3'
export const ATTEMPT_QUEUE_STORAGE_KEY = 'aulas:offline-attempts:v2'
export const LEGACY_ATTEMPT_QUEUE_STORAGE_KEY = 'aulas:offline-attempts:v1'
export const MAX_ATTEMPTS_PER_USER = 100
const STORES = ['attempts', 'receipts', 'migration']
const deletedUserKey = (userId: number) => `deleted-user:${userId}`

export class QueueStorageError extends Error {
  constructor(message = 'Não foi possível gravar a fila neste navegador. A resposta continua na tela; não feche a página.') {
    super(message)
    this.name = 'QueueStorageError'
  }
}

function storageError(error: unknown): QueueStorageError {
  if (error instanceof QueueStorageError) return error
  return new QueueStorageError(error instanceof DOMException && error.name === 'QuotaExceededError'
    ? 'O armazenamento está cheio. A nova resposta não foi salva; as anteriores foram preservadas. Mantenha esta página aberta.'
    : undefined)
}

function positive(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value > 0
}

function parseAttempt(value: unknown): QueuedAttempt {
  if (!value || typeof value !== 'object') throw new QueueStorageError('Há dados inválidos na fila antiga. A cópia original foi preservada; não limpe os dados do navegador.')
  const v = value as Partial<QueuedAttempt>
  if (!positive(v.userId) || !positive(v.exerciseId) || typeof v.answer !== 'string'
    || typeof v.idempotencyKey !== 'string' || !v.idempotencyKey.trim()
    || typeof v.createdAt !== 'string' || !Number.isFinite(Date.parse(v.createdAt))
    || (v.sessionId !== undefined && !positive(v.sessionId))
    || (v.lessonNumber !== undefined && !positive(v.lessonNumber))
    || (v.courseSlug !== undefined && (typeof v.courseSlug !== 'string' || !v.courseSlug.trim()))
    || (v.syncFailure !== undefined && (!v.syncFailure || !Number.isInteger(v.syncFailure.status)
      || v.syncFailure.status < 400 || v.syncFailure.status > 599
      || typeof v.syncFailure.failedAt !== 'string' || !Number.isFinite(Date.parse(v.syncFailure.failedAt))))) {
    throw new QueueStorageError('Há dados inválidos na fila. A cópia original foi preservada; não limpe os dados do navegador.')
  }
  return {
    userId: v.userId, exerciseId: v.exerciseId, answer: v.answer,
    idempotencyKey: v.idempotencyKey, createdAt: v.createdAt,
    ...(v.sessionId === undefined ? {} : { sessionId: v.sessionId }),
    ...(v.courseSlug === undefined ? {} : { courseSlug: v.courseSlug }),
    ...(v.lessonNumber === undefined ? {} : { lessonNumber: v.lessonNumber }),
    ...(v.syncFailure === undefined ? {} : { syncFailure: { ...v.syncFailure } }),
  }
}

function stripLegacyUser(userId: number): void {
  for (const [key, version] of [
    [LEGACY_ATTEMPT_QUEUE_STORAGE_KEY, 1],
    [ATTEMPT_QUEUE_STORAGE_KEY, 2],
  ] as const) {
    const source = readLocal(key)
    if (!source.ok) throw new QueueStorageError(source.error)
    if (source.value === null) continue
    try {
      const parsed: unknown = JSON.parse(source.value)
      const items = version === 1 ? parsed
        : parsed && typeof parsed === 'object' && 'version' in parsed
          && parsed.version === 2 && 'attempts' in parsed ? parsed.attempts : null
      if (!Array.isArray(items)) throw new Error('Invalid legacy envelope')
      const remaining = items.filter((item) => (
        !item || typeof item !== 'object' || (item as { userId?: unknown }).userId !== userId
      ))
      if (remaining.length === items.length) continue
      const result = remaining.length === 0
        ? removeLocal(key)
        : writeLocal(key, JSON.stringify(version === 1 ? remaining : {
          version: 2, attempts: remaining,
        }))
      if (!result.ok) throw new QueueStorageError(result.error)
    } catch (error) {
      throw error instanceof QueueStorageError ? error
        : new QueueStorageError('A fila antiga está inválida e não pôde ser limpa com segurança.')
    }
  }
}

function merge(previous: QueuedAttempt, next: QueuedAttempt): QueuedAttempt {
  if (previous.exerciseId !== next.exerciseId || previous.answer !== next.answer
    || (['sessionId', 'courseSlug', 'lessonNumber'] as const).some((key) => (
      previous[key] !== undefined && next[key] !== undefined && previous[key] !== next[key]
    ))) {
    throw new QueueStorageError('Duas respostas diferentes usam a mesma chave. Nenhuma foi sobrescrita; preserve esta página e as filas antigas.')
  }
  return { ...next, ...previous, // Preserva resposta/data/bloqueio já conhecidos.
    sessionId: previous.sessionId ?? next.sessionId,
    courseSlug: previous.courseSlug ?? next.courseSlug,
    lessonNumber: previous.lessonNumber ?? next.lessonNumber,
    syncFailure: previous.syncFailure ?? next.syncFailure,
  }
}

function request<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (!globalThis.indexedDB) { reject(new QueueStorageError()); return }
    const req = indexedDB.open(ATTEMPT_QUEUE_DB, 1)
    let blocked = false
    req.onupgradeneeded = () => {
      const db = req.result
      db.createObjectStore('attempts', { keyPath: ['userId', 'idempotencyKey'] }).createIndex('user', 'userId')
      db.createObjectStore('receipts', { keyPath: ['userId', 'idempotencyKey'] })
      db.createObjectStore('migration')
    }
    req.onerror = () => reject(req.error)
    req.onblocked = () => {
      blocked = true
      reject(new QueueStorageError('Feche as abas antigas deste aplicativo e tente abrir a fila novamente. Nenhuma resposta foi removida.'))
    }
    req.onsuccess = () => {
      if (blocked) { req.result.close(); return }
      req.result.onversionchange = () => req.result.close()
      resolve(req.result)
    }
  })
}

/** Somente awaits de requests IDB dentro de work, nunca rede/timers. O sucesso
 * é publicado em oncomplete, não no onsuccess de uma gravação individual. */
function transaction<T>(db: IDBDatabase, stores: string[], mode: IDBTransactionMode,
  work: (tx: IDBTransaction) => Promise<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(stores, mode)
    let result: T
    let failure: unknown
    tx.oncomplete = () => resolve(result)
    tx.onabort = () => reject(storageError(failure ?? tx.error))
    void work(tx).then((value) => { result = value }).catch((error: unknown) => {
      failure = error
      try { tx.abort() } catch { reject(storageError(error)) }
    })
  })
}

async function migrate(db: IDBDatabase): Promise<void> {
  const sources = [LEGACY_ATTEMPT_QUEUE_STORAGE_KEY, ATTEMPT_QUEUE_STORAGE_KEY].map((key, index) => {
    const source = readLocal(key)
    if (!source.ok) throw new QueueStorageError(source.error)
    const raw = source.value
    if (raw === null) return { key, raw, attempts: [] as QueuedAttempt[] }
    try {
      const parsed: unknown = JSON.parse(raw)
      const items = index === 0 ? parsed
        : parsed && typeof parsed === 'object' && 'version' in parsed && parsed.version === 2 && 'attempts' in parsed
          ? parsed.attempts : null
      if (!Array.isArray(items)) throw new Error('Invalid legacy envelope')
      return { key, raw, attempts: items.map(parseAttempt) }
    } catch (error) {
      throw error instanceof QueueStorageError ? error
        : new QueueStorageError('Não foi possível ler a fila antiga. A cópia original foi preservada; não limpe os dados do navegador.')
    }
  })
  await transaction(db, STORES, 'readwrite', async (tx) => {
    const attempts = tx.objectStore('attempts')
    const receipts = tx.objectStore('receipts')
    const migration = tx.objectStore('migration')
    for (const source of sources) {
      if (source.raw === null || await request(migration.get(source.key)) === source.raw) continue
      for (const item of source.attempts) {
        if (await request(migration.get(deletedUserKey(item.userId)))) continue
        const key = [item.userId, item.idempotencyKey]
        if (await request(receipts.get(key))) continue
        const previous = await request<QueuedAttempt | undefined>(attempts.get(key))
        await request(attempts.put(previous ? merge(previous, item) : item))
      }
      await request(migration.put(source.raw, source.key))
    }
  })
  // Não apagar nem reescrever localStorage: uma aba antiga pode modificá-lo
  // entre leitura e remoção. Novos snapshots serão importados; recibos impedem
  // que a cópia antiga ressuscite uma tentativa já confirmada/descartada.
}

async function withDatabase<T>(work: (db: IDBDatabase) => Promise<T>): Promise<T> {
  let db: IDBDatabase | undefined
  try {
    db = await open()
    await migrate(db)
    return await work(db)
  } catch (error) {
    throw storageError(error)
  } finally { db?.close() }
}

export const attemptStore = {
  list(userId: number): Promise<QueuedAttempt[]> {
    return withDatabase((db) => transaction(db, ['attempts'], 'readonly', async (tx) => {
      const items = await request<QueuedAttempt[]>(tx.objectStore('attempts').index('user').getAll(userId))
      return items.sort((a, b) => a.createdAt.localeCompare(b.createdAt) || a.idempotencyKey.localeCompare(b.idempotencyKey))
    }))
  },
  add(value: QueuedAttempt): Promise<boolean> {
    const item = parseAttempt(value)
    return withDatabase((db) => transaction(db, STORES, 'readwrite', async (tx) => {
      const store = tx.objectStore('attempts')
      const key = [item.userId, item.idempotencyKey]
      if (await request(tx.objectStore('migration').get(deletedUserKey(item.userId)))) {
        throw new QueueStorageError('Os dados locais desta conta já foram removidos.')
      }
      if (await request(tx.objectStore('receipts').get(key))) {
        throw new QueueStorageError('Esta tentativa já foi processada. Atualize o resultado antes de responder novamente.')
      }
      const previous = await request<QueuedAttempt | undefined>(store.get(key))
      if (previous) { merge(previous, item); return false }
      if (await request(store.index('user').count(item.userId)) >= MAX_ATTEMPTS_PER_USER) {
        throw new QueueStorageError(`Sua fila atingiu ${MAX_ATTEMPTS_PER_USER} respostas. Sincronize as pendências antes de salvar outra. A nova resposta continua apenas na tela.`)
      }
      await request(store.add(item))
      return true
    }))
  },
  block(userId: number, idempotencyKey: string, status: number): Promise<void> {
    return withDatabase((db) => transaction(db, ['attempts'], 'readwrite', async (tx) => {
      const store = tx.objectStore('attempts')
      const item = await request<QueuedAttempt | undefined>(store.get([userId, idempotencyKey]))
      if (item) await request(store.put({ ...item, syncFailure: { status, failedAt: new Date().toISOString() } }))
    }))
  },
  finish(userId: number, idempotencyKey: string): Promise<void> {
    return withDatabase((db) => transaction(db, ['attempts', 'receipts'], 'readwrite', async (tx) => {
      await request(tx.objectStore('receipts').put({ userId, idempotencyKey }))
      await request(tx.objectStore('attempts').delete([userId, idempotencyKey]))
    }))
  },
  discardBlocked(userId: number, keys?: string[]): Promise<void> {
    return withDatabase((db) => transaction(db, ['attempts', 'receipts'], 'readwrite', async (tx) => {
      const store = tx.objectStore('attempts')
      const items = await request<QueuedAttempt[]>(store.index('user').getAll(userId))
      for (const item of items) {
        if (!item.syncFailure || (keys && !keys.includes(item.idempotencyKey))) continue
        await request(tx.objectStore('receipts').put({ userId, idempotencyKey: item.idempotencyKey }))
        await request(store.delete([userId, item.idempotencyKey]))
      }
    }))
  },
  deleteUser(userId: number): Promise<void> {
    return withDatabase((db) => transaction(db, STORES, 'readwrite', async (tx) => {
      const attempts = tx.objectStore('attempts')
      const receipts = tx.objectStore('receipts')
      await request(tx.objectStore('migration').put(true, deletedUserKey(userId)))
      for (const item of await request<QueuedAttempt[]>(attempts.index('user').getAll(userId))) {
        await request(attempts.delete([userId, item.idempotencyKey]))
      }
      for (const receipt of await request<{ userId: number; idempotencyKey: string }[]>(
        receipts.getAll(),
      )) {
        if (receipt.userId === userId) {
          await request(receipts.delete([userId, receipt.idempotencyKey]))
        }
      }
    })).then(() => { stripLegacyUser(userId) })
  },
}
