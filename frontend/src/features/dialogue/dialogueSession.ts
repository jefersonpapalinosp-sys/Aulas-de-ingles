import type { SpeakingPolicy } from '../../api/client'
import { DialogueError, dialogueError } from './dialogueTransport'
import type { Creation, Dialogue, DialogueTransport, Mode, Rating } from './dialogueTransport'

export type Phase = 'idle' | 'listening' | 'uploading' | 'waiting' | 'partner_speaking' | 'error'
export type DialogueState = {
  phase: Phase
  dialogue: Dialogue | null
  message: string
  pendingInput: boolean
  awaiting: boolean
  revision: number
}
type Pending = { position: number; key: string } & ({ text: string } | { blob: Blob })

/** Conteúdo fica só na memória; retry conserva posição/chave/bytes e nunca troca de conta. */
export class DialogueSession {
  private state: DialogueState = { phase: 'idle', dialogue: null, message: '', pendingInput: false, awaiting: false, revision: 0 }
  private listeners = new Set<() => void>()
  private controller: AbortController | null = null
  private timer: ReturnType<typeof setTimeout> | null = null
  private generation = 0
  private pending: Pending | null = null
  private creation: Creation | null = null
  private polls = 0

  constructor(readonly userId: number, private transport: DialogueTransport, private pollMs = 1500) {}
  snapshot = () => this.state
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener) } }
  private publish(patch: Partial<DialogueState>) {
    this.state = { ...this.state, ...patch }
    this.listeners.forEach((listener) => listener())
  }
  dispose = () => {
    this.generation++
    this.controller?.abort()
    this.controller = null
    if (this.timer) clearTimeout(this.timer)
    this.timer = null
  }
  private async run(phase: Phase, work: (signal: AbortSignal, current: () => boolean) => Promise<void>) {
    if (this.controller) return
    const account = this.transport.session()
    if (account.usuarioId !== this.userId || !account.token || account.perfilNaoConfirmado) {
      this.publish({ phase: 'error', message: 'Confirme a sessão da mesma conta para continuar.' })
      return
    }
    const controller = new AbortController()
    this.controller = controller
    const generation = this.generation
    const current = () => !controller.signal.aborted && this.generation === generation
      && this.transport.session().geracao === account.geracao
      && this.transport.session().usuarioId === this.userId
    this.publish({ phase, message: '' })
    try { await work(controller.signal, current) }
    catch (error) {
      if (current()) {
        // Recusas definitivas permitem corrigir a entrada; perda de resposta exige retry idêntico.
        if (error instanceof DialogueError && [413, 415, 422, 429].includes(error.status)) this.pending = null
        this.publish({ phase: 'error', message: dialogueError(error), pendingInput: this.pending !== null })
      }
    } finally {
      if (this.controller === controller) this.controller = null
      if (!controller.signal.aborted && !current()) {
        this.publish({ phase: 'error', message: 'A sessão mudou. Volte à mesma conta para continuar.' })
      }
    }
  }
  open = async (lessonId: number, mode: Mode, speaker: string | null) => {
    if (this.state.dialogue || this.state.pendingInput || this.state.awaiting) return
    if (!this.creation || this.creation.mode !== mode || this.creation.partner_speaker !== speaker) {
      this.creation = { lesson_id: lessonId, mode, partner_speaker: speaker, operation_key: crypto.randomUUID() }
    }
    const body = this.creation
    await this.run('uploading', async (signal, current) => {
      const dialogue = await this.transport.create(body, signal)
      if (current()) { this.creation = null; this.publish({ dialogue, phase: 'idle' }) }
    })
  }
  private async load(id: number, signal: AbortSignal, current: () => boolean) {
    const dialogue = await this.transport.read(id, signal)
    if (!current()) return
    const awaiting = dialogue.turns.some((turn) => turn.state === 'pending')
    this.publish({ dialogue, awaiting, phase: awaiting ? 'waiting' : 'idle', revision: this.state.revision + 1 })
    if (awaiting) {
      if (++this.polls >= 40) {
        this.publish({ phase: 'error', message: 'O processamento continua na fila. Consulte novamente em instantes.' })
        return
      }
      this.timer = setTimeout(() => { this.timer = null; void this.refresh() }, this.pollMs)
    } else this.polls = 0
  }
  refresh = async () => {
    const id = this.state.dialogue?.id
    if (id === undefined) return
    if (this.timer) clearTimeout(this.timer)
    this.timer = null
    await this.run('waiting', (signal, current) => this.load(id, signal, current))
  }
  retry = async () => {
    this.polls = 0
    if (this.pending) await this.sendPending()
    else await this.refresh()
  }
  private canSend() {
    return this.state.dialogue && this.state.dialogue.turns_remaining > 0
      && !this.controller && !this.pending && !this.state.awaiting && this.state.phase !== 'listening'
      && this.state.phase !== 'partner_speaking'
  }
  sendText = async (text: string) => {
    if (!this.canSend() || !text.trim() || text.length > 2000) return
    this.pending = { text, key: crypto.randomUUID(), position: this.nextPosition() }
    await this.sendPending()
  }
  sendAudio = async (blob: Blob, duration: number, consent: boolean, policy: SpeakingPolicy) => {
    if (!this.canSend() || this.state.dialogue?.mode !== 'guided' || !consent) return
    if (blob.size === 0 || blob.size > policy.max_bytes || duration > policy.max_duration_ms
      || !policy.mime_types.includes(blob.type.split(';')[0]!)) {
      this.publish({ phase: 'error', message: 'Confira o tamanho, a duração e o formato da gravação antes de enviar.' })
      return
    }
    this.pending = { blob, key: crypto.randomUUID(), position: this.nextPosition() }
    await this.sendPending()
  }
  private nextPosition() { return Math.max(0, ...this.state.dialogue!.turns.map((turn) => turn.position)) + 1 }
  private async sendPending() {
    const input = this.pending
    const id = this.state.dialogue?.id
    if (!input || id === undefined) return
    this.publish({ pendingInput: true })
    await this.run('uploading', async (signal, current) => {
      if ('text' in input) await this.transport.text(id, input.position, { text: input.text, idempotency_key: input.key }, signal)
      else await this.transport.audio(id, input.position, input.blob, signal)
      if (!current()) return
      this.pending = null
      this.publish({ pendingInput: false, awaiting: true })
      await this.load(id, signal, current)
    })
  }
  rate = async (position: number, rating: Rating) => {
    const id = this.state.dialogue?.id
    if (id === undefined) return
    await this.run('uploading', async (signal, current) => {
      await this.transport.rate(id, position, rating, signal)
      if (current()) await this.load(id, signal, current)
    })
  }
  leave = () => {
    if (this.pending || this.state.awaiting || this.controller) return
    this.dispose()
    this.creation = null
    this.publish({ dialogue: null, phase: 'idle', message: '', pendingInput: false, awaiting: false })
  }
  remove = async () => {
    const id = this.state.dialogue?.id
    if (id === undefined) return
    this.dispose()
    await this.run('uploading', async (signal, current) => {
      await this.transport.remove(id, signal)
      if (current()) {
        this.pending = null
        this.creation = null
        this.publish({ dialogue: null, phase: 'idle', pendingInput: false, awaiting: false, message: 'Conversa excluída.' })
      }
    })
  }
  listening = (active: boolean) => {
    if (!this.controller && !this.state.awaiting && !this.pending) this.publish({ phase: active ? 'listening' : 'idle', message: '' })
  }
  speaking = (active: boolean) => {
    if (!this.controller && !this.state.awaiting) this.publish({ phase: active ? 'partner_speaking' : 'idle' })
  }
}
