import { api } from '../../api/client'
import { ApiError } from '../../api/errors'
import { respondNative } from '../../api/nativeListening'
import { sessionSnapshot } from '../../api/session'
import { nativeStore, type NativeCommand } from './nativeStore'

export function nativeAllowed(userId: number) {
  const session = sessionSnapshot()
  return navigator.onLine && session.usuarioId === userId && !!session.token && !session.perfilNaoConfirmado
}
export async function readNativeSession(id: number) {
  const { data, response } = await api.GET('/api/listening/sessions/{session_id}', { params: { path: { session_id: id } } })
  if (!data) throw new ApiError('a sessão de listening', response)
  return data
}
const active = new Map<number, Promise<void>>()
export function syncNative(userId: number): Promise<void> {
  const running = active.get(userId)
  if (running) return running
  const run = async () => {
    const generation = sessionSnapshot().geracao
    const allowed = () => nativeAllowed(userId) && sessionSnapshot().geracao === generation
    const held = new Set<number>()
    for (let count = 0; count < 100 && allowed(); count++) {
      const local = await nativeStore.read(userId)
      for (const command of local.commands) if (command.blocked) held.add(command.sessionId)
      const command = local.commands.find(row => !held.has(row.sessionId))
      if (!command || !allowed()) break
      try {
        const response = await respondNative(command.sessionId, command.body)
        if (!allowed()) return
        await nativeStore.acknowledge(userId, local.epoch, command, response)
      } catch (error) {
        if (!allowed()) return
        if (error instanceof ApiError && typeof error.status === 'number' && [404, 409, 410, 422].includes(error.status)) {
          await nativeStore.block(userId, local.epoch, command, error.status)
          held.add(command.sessionId)
        } else throw error
      }
    }
  }
  const task = Promise.resolve(navigator.locks ? navigator.locks.request(`native-listening-sync:${userId}`, {}, run) : run()).then(() => undefined)
    .finally(() => { active.delete(userId) })
  active.set(userId, task)
  return task
}
export async function resolveNative(userId: number, epoch: number, command: NativeCommand) {
  if (!nativeAllowed(userId)) throw new Error('Confirme a conta e a conexão antes de resolver.')
  const generation = sessionSnapshot().geracao
  const current = await readNativeSession(command.sessionId)
  if (!nativeAllowed(userId) || sessionSnapshot().geracao !== generation) throw new Error('A conta mudou.')
  await nativeStore.rebase(userId, epoch, command.id, current)
  await syncNative(userId)
}
