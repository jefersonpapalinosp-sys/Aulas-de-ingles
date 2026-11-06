import type { NativeResponse, NativeSession } from '../../api/nativeListening'

export const NATIVE_DB = 'aulas:listening:v1'
export const NATIVE_EVENT = 'aulas:listening-change'
type Base = { id: string; userId: number; sessionId: number; slug: string; version: number; createdAt: string }
export type NativeDraft = Base & { kind: 'draft'; questionId: string; selected: string[]; editorId?: string }
export type NativeCommand = Base & { kind: 'command'; body: NativeResponse; blocked: boolean; status?: number }
type Snapshot = Base & { kind: 'snapshot'; session: NativeSession }
type RecordValue = NativeDraft | NativeCommand | Snapshot
export type NativeLocal = { epoch: number; drafts: NativeDraft[]; commands: NativeCommand[]; sessions: NativeSession[] }

export class NativeStorageError extends Error {
  constructor() { super('Não foi possível salvar o listening neste dispositivo. Mantenha a página aberta; os dados anteriores foram preservados.') }
}

function request<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(new NativeStorageError())
  })
}
async function database() {
  const req = indexedDB.open(NATIVE_DB, 1)
  req.onupgradeneeded = () => {
    req.result.createObjectStore('records', { keyPath: 'id' }).createIndex('user', 'userId')
    req.result.createObjectStore('guards')
  }
  let blocked = false
  const db = await new Promise<IDBDatabase>((resolve, reject) => {
    req.onblocked = () => { blocked = true; reject(new NativeStorageError()) }
    req.onerror = () => reject(new NativeStorageError())
    req.onsuccess = () => { if (blocked) req.result.close(); else resolve(req.result) }
  })
  db.onversionchange = () => db.close()
  return db
}
function notify(userId: number) {
  window.dispatchEvent(new CustomEvent(NATIVE_EVENT, { detail: userId }))
  if (typeof BroadcastChannel !== 'undefined') {
    const channel = new BroadcastChannel(NATIVE_EVENT)
    channel.postMessage(userId); channel.close()
  }
}

/** Só awaits de IndexedDB dentro da transação. Sucesso significa oncomplete. */
async function transact<T>(userId: number, epoch: number | null, write: boolean,
  work: (store: IDBObjectStore, rows: RecordValue[], generation: number, guards: IDBObjectStore) => T | Promise<T>): Promise<T> {
  let db: IDBDatabase | undefined
  try {
    db = await database()
    const result = await new Promise<T>((resolve, reject) => {
      const tx = db!.transaction(['records', 'guards'], write ? 'readwrite' : 'readonly')
      let value: T
      tx.oncomplete = () => resolve(value)
      tx.onabort = () => reject(new NativeStorageError())
      void (async () => {
        const guards = tx.objectStore('guards')
        const generation = (await request(guards.get(userId)) as number | undefined) ?? 0
        if (epoch !== null && epoch !== generation) throw new NativeStorageError()
        const store = tx.objectStore('records')
        const rows = await request(store.index('user').getAll(userId)) as RecordValue[]
        if (rows.some(row => row.userId !== userId)) throw new NativeStorageError()
        value = await work(store, rows, generation, guards)
      })().catch(() => { try { tx.abort() } catch { reject(new NativeStorageError()) } })
    })
    if (write) notify(userId)
    return result
  } catch { throw new NativeStorageError() } finally { db?.close() }
}

const base = (userId: number, session: NativeSession, id: string): Base => ({
  id, userId, sessionId: session.id, slug: session.activity.slug, version: session.activity.version,
  createdAt: new Date().toISOString(),
})
function snapshot(store: IDBObjectStore, rows: RecordValue[], userId: number, session: NativeSession) {
  const id = `snapshot:${userId}:${session.id}`
  const previous = rows.find(row => row.id === id)
  if (previous?.kind === 'snapshot' && previous.session.revision > session.revision) return
  store.put({ ...base(userId, session, id), kind: 'snapshot', session } satisfies Snapshot)
}
function room(rows: RecordValue[]) { if (rows.length >= 1000) throw new NativeStorageError() }

export const nativeStore = {
  read(userId: number): Promise<NativeLocal> {
    return transact(userId, null, false, (_store, rows, epoch) => ({ epoch,
      drafts: rows.filter((row): row is NativeDraft => row.kind === 'draft'),
      commands: rows.filter((row): row is NativeCommand => row.kind === 'command')
        .sort((a, b) => a.sessionId - b.sessionId || a.body.expected_revision - b.body.expected_revision),
      sessions: rows.filter((row): row is Snapshot => row.kind === 'snapshot').map(row => row.session),
    }))
  },
  cache(userId: number, epoch: number, session: NativeSession) {
    return transact(userId, epoch, true, (store, rows) => { room(rows); snapshot(store, rows, userId, session) })
  },
  draft(userId: number, epoch: number, session: NativeSession, questionId: string, selected: string[], previousId?: string, editorId?: string) {
    return transact(userId, epoch, true, (store, rows) => {
      room(rows)
      const row: NativeDraft = { ...base(userId, session, crypto.randomUUID()), kind: 'draft', questionId, selected, editorId }
      const previous = rows.find(item => item.id === previousId)
      // Só substitui o rascunho que esta aba leu. Uma edição concorrente vira outra variante.
      if (previous?.kind === 'draft' && previous.sessionId === session.id && previous.questionId === questionId && previous.editorId === editorId) store.delete(previous.id)
      store.put(row)
      return row
    })
  },
  enqueue(userId: number, epoch: number, session: NativeSession, input: NativeResponse, draftId?: string) {
    return transact(userId, epoch, true, (store, rows) => {
      room(rows)
      const commands = rows.filter((row): row is NativeCommand => row.kind === 'command' && row.sessionId === session.id)
      if (commands.some(row => row.blocked) || commands.length >= 100) throw new NativeStorageError()
      const cached = rows.find(row => row.kind === 'snapshot' && row.sessionId === session.id) as Snapshot | undefined
      const revision = Math.max(session.revision, cached?.session.revision ?? 0,
        ...commands.map(row => row.body.expected_revision + 1))
      if (revision >= 100) throw new NativeStorageError()
      const command: NativeCommand = { ...base(userId, session, `command:${userId}:${input.operation_key}`), kind: 'command',
        body: { ...input, expected_revision: revision }, blocked: false }
      if (rows.some(row => row.id === command.id)) throw new NativeStorageError()
      snapshot(store, rows, userId, session)
      store.add(command)
      const draft = rows.find(row => row.id === draftId)
      if (draft?.kind === 'draft' && draft.sessionId === session.id && draft.questionId === input.question_id) store.delete(draft.id)
      return command
    })
  },
  acknowledge(userId: number, epoch: number, command: NativeCommand, session: NativeSession) {
    return transact(userId, epoch, true, (store, rows) => {
      if (session.id !== command.sessionId || session.activity.version !== command.version || session.activity.slug !== command.slug) throw new NativeStorageError()
      snapshot(store, rows, userId, session)
      const current = rows.find(row => row.id === command.id)
      if (current?.kind === 'command') store.delete(current.id)
    })
  },
  block(userId: number, epoch: number, command: NativeCommand, status: number) {
    return transact(userId, epoch, true, (store, rows) => {
      const current = rows.find(row => row.id === command.id)
      if (current?.kind === 'command') store.put({ ...current, blocked: true, status })
    })
  },
  remove(userId: number, epoch: number, id: string) {
    return transact(userId, epoch, true, (store, rows) => {
      if (rows.some(row => row.id === id && row.kind !== 'snapshot')) store.delete(id)
    })
  },
  rebase(userId: number, epoch: number, id: string, session: NativeSession) {
    return transact(userId, epoch, true, (store, rows) => {
      const old = rows.find(row => row.id === id)
      if (old?.kind !== 'command' || !old.blocked || old.sessionId !== session.id || old.version !== session.activity.version) throw new NativeStorageError()
      const key = crypto.randomUUID()
      store.add({ ...old, id: `command:${userId}:${key}`, blocked: false, status: undefined,
        body: { ...old.body, operation_key: key, expected_revision: session.revision } })
      store.delete(old.id)
      snapshot(store, rows, userId, session)
    })
  },
  clear(userId: number) {
    return transact(userId, null, true, (store, rows, epoch, guards) => {
      for (const row of rows) store.delete(row.id)
      guards.put(epoch + 1, userId)
      return rows.length
    })
  },
}
