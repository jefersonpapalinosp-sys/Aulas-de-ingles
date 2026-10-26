import { readLocal, removeLocal, writeLocal } from '../../storage/local'
import type { PracticeSession } from './types'

/** Motor da posição da sessão de prática.
 *
 * A posição é a única coisa que o aluno perde ao sair do ar no meio de uma
 * sessão, então ela é espelhada no dispositivo antes de qualquer rede e só sai
 * do espelho quando a conta confirma. A chave de idempotência é reaproveitada
 * na segunda tentativa de propósito: ela cobre tanto a revisão concorrente
 * quanto a resposta perdida depois de o primeiro PUT já ter sido aplicado.
 */

export type PracticePositionState = {
  /** Posição que só existe neste dispositivo; `null` quer dizer "igual à conta". */
  local: number | null
  storageWarning: string
  error: string
}

export type PracticePositionTransport = {
  save: (command: {
    sessionId: number
    currentPosition: number
    expectedRevision: number
    idempotencyKey: string
  }) => Promise<unknown>
  /** Relê a sessão na conta; `null` quando não foi possível. */
  reload: () => Promise<PracticeSession | null>
}

export function practicePositionKey(userId: number, sessionId: number): string {
  return `aulas-ingles:practice-position:v1:${userId}:${sessionId}`
}

export class PracticePosition {
  private active = true
  private syncing = false
  private listeners = new Set<() => void>()
  private state: PracticePositionState = { local: null, storageWarning: '', error: '' }

  constructor(readonly userId: number, private transport: PracticePositionTransport) {}

  snapshot = () => this.state
  subscribe = (listener: () => void) => {
    this.listeners.add(listener)
    return () => { this.listeners.delete(listener) }
  }
  dispose = () => { this.active = false }

  private publish(patch: Partial<PracticePositionState>) {
    if (!this.active) return
    this.state = { ...this.state, ...patch }
    this.listeners.forEach((listener) => listener())
  }

  private mirror(sessionId: number, position: number | null) {
    const key = practicePositionKey(this.userId, sessionId)
    return position === null ? removeLocal(key) : writeLocal(key, String(position))
  }

  /** Troca de sessão: nada se sabe da posição local até ler o espelho dela. */
  reset = () => { this.publish({ local: null, error: '', storageWarning: '' }) }

  /** Lê o espelho desta sessão, descartando posição que o pack não tem mais. */
  load = (session: PracticeSession) => {
    const stored = readLocal(practicePositionKey(this.userId, session.id))
    if (!stored.ok) {
      this.publish({ storageWarning: stored.error })
      return
    }
    const position = stored.value === null ? null : Number(stored.value)
    const known = session.items.some((item) => item.position === position)
    this.publish({ local: known ? position : null })
  }

  /** Espelha a posição na hora; a conta vem depois, e só se houver rede. */
  moveTo = async (session: PracticeSession, position: number, online: boolean) => {
    if (!session.items.some((item) => item.position === position)) return
    const saved = this.mirror(session.id, position)
    this.publish({
      local: position,
      error: '',
      storageWarning: saved.ok ? '' : `${saved.error} Posição apenas nesta tela até sincronizar.`,
    })
    if (!online) return
    await this.reconcile(session, position)
  }

  /** Alinha espelho e conta. Chamado quando a rede volta ou a sessão recarrega. */
  settle = async (session: PracticeSession, online: boolean) => {
    const position = this.state.local
    if (!online || position === null) return
    if (session.current_position === position) {
      this.forget(session.id)
      return
    }
    await this.reconcile(session, position)
  }

  /** Esquece o espelho só se ele ainda for a posição que a conta confirmou.
   *
   * Uma confirmação em voo pode chegar depois de o aluno ter avançado de novo:
   * apagar o espelho ali perderia a navegação mais nova, que é a única que
   * existe fora desta tela.
   */
  private forget(sessionId: number, confirmed?: number) {
    if (confirmed !== undefined && this.state.local !== confirmed) {
      this.publish({ error: '' })
      return
    }
    const removed = this.mirror(sessionId, null)
    this.publish({ local: null, error: '', storageWarning: removed.ok ? '' : removed.error })
  }

  private async reconcile(baseline: PracticeSession, position: number): Promise<boolean> {
    if (this.syncing) return false
    this.syncing = true
    const idempotencyKey = crypto.randomUUID()
    try {
      try {
        await this.transport.save({
          sessionId: baseline.id,
          currentPosition: position,
          expectedRevision: baseline.state_revision,
          idempotencyKey,
        })
      } catch (initialError) {
        const latest = await this.transport.reload()
        if (!latest || latest.id !== baseline.id) throw initialError
        if (latest.current_position !== position) {
          // Conteúdo trocado ou sessão encerrada não recebem posição nova: a
          // tela precisa mostrar o aviso próprio em vez de insistir.
          if (latest.status !== 'active' || latest.content_changed) throw initialError
          await this.transport.save({
            sessionId: latest.id,
            currentPosition: position,
            expectedRevision: latest.state_revision,
            idempotencyKey,
          })
        }
      }
      this.forget(baseline.id, position)
      return true
    } catch {
      this.publish({
        error: 'Posição não sincronizada. Confira o salvamento local antes de sair e tente novamente.',
      })
      return false
    } finally {
      this.syncing = false
    }
  }
}
