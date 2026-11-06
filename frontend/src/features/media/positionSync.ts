// Retirada do adaptador legado: alvo 2027-01-29, condicionada à preservação/recuperação.
// Critérios: docs/politica_migracoes_storage_2026-10-29.md. Não expira nem apaga dados.
import type { components } from '../../api/schema'
import { listLocal, readLocal, removeLocal, writeLocal } from '../../storage/local'

export type Position = components['schemas']['MediaPositionOut']
export type PositionCommand = components['schemas']['MediaPositionIn']
export class PositionConflict extends Error {
  constructor(readonly current: Position) { super('A posição mudou em outra sessão.') }
}
type Transport = { read: () => Promise<Position>; save: (body: PositionCommand) => Promise<Position>; allowed: () => boolean }
export type PositionState = {
  position: number; completed: boolean; pending: number; ready: boolean; confirmed: boolean
  conflict: Position | null; error: string; warning: string
}

function validCommand(value: unknown): value is PositionCommand {
  if (!value || typeof value !== 'object') return false
  const c = value as PositionCommand
  return Number.isFinite(c.position_seconds) && c.position_seconds >= 0
    && Number.isInteger(c.expected_revision) && c.expected_revision >= 0
    && typeof c.operation_key === 'string' && /^[a-f0-9-]{36}$/i.test(c.operation_key)
    && typeof c.changed_at === 'string' && Number.isFinite(Date.parse(c.changed_at))
    && typeof c.completed === 'boolean' && (!c.completed || c.position_seconds === 0)
}

/** Só a última posição ainda não enviada por esta instância pode ser combinada.
 * Web Locks exclui envio por outra aba durante a alteração. Após despacho, chave,
 * conteúdo e revisão são imutáveis, inclusive quando a resposta se perde. */
export class PositionSync {
  readonly prefix: string
  private cacheKey: string
  private queue: (PositionCommand & { dispatched?: boolean })[] = []
  private mutableKey: string | null = null
  private memoryOnly = new Set<string>()
  private remote: Position | null = null
  private legacy: number | null = null
  private busy = false
  private active = true
  private listeners = new Set<() => void>()
  private state: PositionState = { position: 0, completed: false, pending: 0, ready: false, confirmed: false,
    conflict: null, error: '', warning: '' }

  constructor(readonly userId: number, readonly mediaId: number, private transport: Transport, namespace = 'media') {
    this.prefix = namespace === 'media' ? `aulas-ingles:media-pending:v2:${userId}:${mediaId}:`
      : `aulas-ingles:native-pending:v1:${userId}:${namespace}:${mediaId}:`
    this.cacheKey = namespace === 'media' ? `aulas-ingles:media-position:v2:${userId}:${mediaId}`
      : `aulas-ingles:native-position:v1:${userId}:${namespace}:${mediaId}`
    const cached = readLocal(this.cacheKey)
    if (cached.ok && cached.value) {
      try {
        const value = JSON.parse(cached.value) as Position
        if (Number.isInteger(value.revision) && value.revision >= 0 && Number.isFinite(value.position_seconds)
          && value.media_id === mediaId) this.remote = value
      } catch { this.state.warning = 'Posição local inválida preservada; confira a conta.' }
    } else if (!cached.ok) this.state.warning = cached.error
    if (!this.remote && namespace === 'media') {
      const old = readLocal(`aulas-ingles:media-position:v1:${userId}:${mediaId}`)
      if (old.ok && old.value && Number.isFinite(Number(old.value)) && Number(old.value) > 0) this.legacy = Number(old.value)
    }
    this.reload()
    this.publish({ ready: this.queue.length > 0 || this.remote !== null || this.legacy !== null })
  }

  snapshot = () => this.state
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener) } }
  activate = () => { this.active = true }
  dispose = () => { this.active = false }
  private publish(patch: Partial<PositionState> = {}) {
    const latest = this.queue.at(-1)
    this.state = { ...this.state, position: latest?.position_seconds ?? this.legacy ?? this.remote?.position_seconds ?? 0,
      completed: latest?.completed ?? this.remote?.completed ?? false, pending: this.queue.length, ...patch }
    this.listeners.forEach((listener) => listener())
  }
  private reload() {
    const keys = listLocal(this.prefix)
    if (!keys.ok) { this.state.warning = keys.error; return }
    const present = new Set(keys.value)
    const commands = new Map(this.queue.filter((c) => this.memoryOnly.has(c.operation_key)
      || present.has(this.prefix + c.operation_key)).map((c) => [c.operation_key, c]))
    for (const key of keys.value) {
      const raw = readLocal(key)
      if (!raw.ok) { this.state.warning = raw.error; continue }
      try {
        const command: unknown = JSON.parse(raw.value ?? 'null')
        if (validCommand(command) && key === this.prefix + command.operation_key) commands.set(command.operation_key, command)
        else this.state.warning = 'Há uma posição local inválida; ela foi preservada.'
      } catch { this.state.warning = 'Há uma posição local inválida; ela foi preservada.' }
    }
    this.queue = [...commands.values()].sort((a, b) => a.expected_revision - b.expected_revision || a.changed_at.localeCompare(b.changed_at))
    if (this.queue.length) this.legacy = null
  }

  private async exclusive<T>(work: () => Promise<T> | T, phase = 'write'): Promise<T> {
    return await (navigator.locks
      ? navigator.locks.request(this.prefix + phase, { mode: 'exclusive' }, work)
      : Promise.resolve().then(work))
  }

  record = async (position: number, completed = false) => {
    try { await this.exclusive(() => this.append(position, completed)) }
    catch { this.publish({ error: 'Não foi possível guardar a posição. Mantenha esta página aberta e tente novamente.' }) }
    if (this.transport.allowed() && !this.busy) void this.sync()
  }

  private append(position: number, completed = false) {
    if (!Number.isFinite(position) || position < 0) return
    this.reload()
    const tail = this.queue.at(-1)
    const combine = !!navigator.locks && tail?.operation_key === this.mutableKey && !tail?.dispatched
      && !tail?.completed && !completed
    if (!combine && this.queue.length >= 1000) {
      this.publish({ error: 'Fila de posições cheia. Reconecte e resolva a sincronização antes de salvar mais.' })
      return
    }
    const command: PositionCommand = { position_seconds: completed ? 0 : position, completed,
      expected_revision: combine ? tail.expected_revision : tail ? tail.expected_revision + 1 : this.remote?.revision ?? 0,
      operation_key: crypto.randomUUID(), changed_at: new Date().toISOString() }
    if (combine) this.queue[this.queue.length - 1] = command
    else this.queue.push(command)
    this.mutableKey = command.operation_key
    this.legacy = null
    const result = writeLocal(this.prefix + command.operation_key, JSON.stringify(command))
    if (!result.ok) this.memoryOnly.add(command.operation_key)
    if (combine && result.ok) {
      const removed = removeLocal(this.prefix + tail.operation_key)
      if (removed.ok) this.memoryOnly.delete(tail.operation_key)
      else this.state.warning = removed.error
    }
    this.publish({ ready: true, confirmed: false, warning: result.ok ? this.state.warning : `${result.error} A retomada local não está garantida.` })
  }

  private acknowledge(command: PositionCommand, remote: Position): boolean {
    this.reload()
    this.remote = remote
    const cached = writeLocal(this.cacheKey, JSON.stringify(remote))
    // Sem cache confirmado mantemos o recibo pendente para recuperar a resposta.
    if (!cached.ok) { this.publish({ warning: cached.error }); return false }
    const removed = removeLocal(this.prefix + command.operation_key)
    if (!removed.ok) { this.publish({ warning: removed.error }); return false }
    this.queue = this.queue.filter((c) => c.operation_key !== command.operation_key)
    this.memoryOnly.delete(command.operation_key)
    return true
  }

  sync = async () => {
    try { await this.exclusive(this.synchronize, 'sync') }
    catch { this.publish({ error: 'Sincronização pausada. As posições locais foram preservadas.' }) }
  }

  private synchronize = async () => {
    if (this.busy || !this.active || !this.transport.allowed() || this.state.conflict) return
    this.busy = true
    try {
      this.reload()
      const remote = await this.transport.read()
      if (!this.active || !this.transport.allowed()) return
      this.remote = remote
      if (this.legacy !== null) {
        if (remote.updated_at !== null) { this.publish({ conflict: remote, ready: true }); return }
        const legacy = this.legacy
        this.legacy = null
        await this.exclusive(() => this.append(legacy))
      }
      this.publish({ ready: true, error: '' })
      while (this.active && this.transport.allowed()) {
        const command = await this.exclusive(() => {
          this.reload()
          const next = this.queue[0]
          if (!next) return
          const current = this.remote!
          if (current.operation_key !== next.operation_key && next.expected_revision !== current.revision) throw new PositionConflict(current)
          // A marca é durável antes de liberar o lock curto para novas posições.
          next.dispatched = true
          const marked = writeLocal(this.prefix + next.operation_key, JSON.stringify(next))
          if (!marked.ok) { this.publish({ warning: marked.error }); return }
          return next
        })
        if (!command || !this.active || !this.transport.allowed()) break
        if (this.remote.operation_key === command.operation_key) {
          const current = this.remote
          if (!await this.exclusive(() => this.acknowledge(command, current))) break
        } else {
          const body: PositionCommand = { position_seconds: command.position_seconds,
            completed: command.completed, expected_revision: command.expected_revision,
            operation_key: command.operation_key, changed_at: command.changed_at }
          const saved = await this.transport.save(body)
          if (!this.active || !this.transport.allowed()) return
          if (!await this.exclusive(() => this.acknowledge(command, saved))) break
        }
        this.publish()
      }
      if (this.queue.length === 0) {
        const cached = writeLocal(this.cacheKey, JSON.stringify(this.remote))
        if (!cached.ok) this.publish({ warning: cached.error })
      }
      this.publish({ confirmed: this.queue.length === 0 })
    } catch (error) {
      if (!this.active) return
      if (error instanceof PositionConflict) this.publish({ conflict: error.current })
      else this.publish({ error: 'Posição pendente. Confira a conexão e a sessão; tente novamente sem limpar os dados locais.' })
    } finally { this.busy = false }
  }

  /** Escolha explícita substitui só os comandos que foram mostrados nesta aba. */
  resolve = async (choice: 'local' | 'remote') => {
    try { await this.exclusive(() => this.resolveLocked(choice), 'sync') }
    catch { this.publish({ error: 'Não foi possível resolver a posição. As posições locais foram preservadas.' }) }
  }

  private resolveLocked = async (choice: 'local' | 'remote') => {
    if (this.busy || !this.transport.allowed()) return
    this.busy = true
    const chosen = { position: this.state.position, completed: this.state.completed }
    const pending = [...this.queue]
    try {
      const remote = await this.transport.read()
      if (!this.active || !this.transport.allowed()) return
      await this.exclusive(() => {
        // Registra a escolha antes de remover comandos anteriores, inclusive após crash.
        const replacement: PositionCommand | null = choice === 'local' ? {
          position_seconds: chosen.position, completed: chosen.completed, expected_revision: remote.revision,
          operation_key: crypto.randomUUID(), changed_at: new Date().toISOString(),
        } : null
        const saved = replacement
          ? writeLocal(this.prefix + replacement.operation_key, JSON.stringify(replacement))
          : writeLocal(this.cacheKey, JSON.stringify(remote))
        if (!saved.ok) { this.publish({ warning: saved.error }); return }
        for (const command of pending) {
          const removed = removeLocal(this.prefix + command.operation_key)
          if (!removed.ok) { this.publish({ warning: removed.error }); return }
          this.memoryOnly.delete(command.operation_key)
        }
        const newer = this.queue.filter((c) => !pending.some((old) => old.operation_key === c.operation_key))
        this.queue = [...(replacement ? [replacement] : []), ...newer]
        this.remote = remote
        this.legacy = null
        this.publish({ conflict: null, error: '', ready: true })
      })
    } catch { this.publish({ error: 'Não foi possível confirmar a posição da conta. Suas posições locais foram preservadas.' }) }
    finally { this.busy = false }
    if (!this.state.conflict) await this.synchronize()
  }
}
