import type { WritingDraft, WritingRevision } from '../../api/client'
import { readLocal, removeLocal, writeLocal } from '../../storage/local'

/** Motor do rascunho: fila serial, revisão imutável e espelho local.
 *
 * Sai do componente por dois motivos. O primeiro é poder provar sem DOM os três
 * casos em que o aluno perde texto se a costura estiver errada: resposta que
 * chega depois do desmonte, conflito entre dispositivos e falha do
 * armazenamento local. O segundo é que a tela do diálogo (IA-47) precisa da
 * mesma máquina de estados, e `features/media/positionSync.ts` já provou o
 * padrão.
 *
 * As chaves do `localStorage` são contrato, não detalhe: o inventário de
 * privacidade conta rascunhos por elas, o logout as preserva e a página de
 * dados pessoais as mostra ao aluno. Mudá-las esconderia texto do dono.
 */

export type DraftStatus = 'idle' | 'saving' | 'saved' | 'local' | 'unsaved'

export type DraftState = {
  text: string
  status: DraftStatus
  hydrated: boolean
  /** Havia cópia local ao abrir: a tela precisa contar isso ao aluno. */
  recovered: boolean
  /** `null` é "nenhuma revisão confirmada", e não "revisão zero". */
  revision: number | null
  conflict: WritingDraft | null
  storageWarning: string
}

export class DraftConflict extends Error {
  constructor(readonly current: WritingDraft) {
    super('O rascunho da conta mudou.')
    this.name = 'DraftConflict'
  }
}

export type DraftTransport = {
  read: () => Promise<WritingDraft>
  save: (body: { text: string; expected_revision: number }) => Promise<WritingDraft>
  createVersion: (body: { text: string; expected_revision: number }) => Promise<WritingRevision>
}

export function draftBackupKey(userId: number, promptId: number): string {
  return `aulas-ingles:writing-draft:v1:${userId}:${promptId}`
}

/** Espera entre a última tecla e o salvamento. */
export const DRAFT_SAVE_DELAY = 700

export class DraftSync {
  readonly key: string
  private queue: Promise<void> = Promise.resolve()
  private timer: number | null = null
  private active = true
  private text = ''
  private queued = ''
  private mirrored: string | null = null
  private revision: number | null = null
  private listeners = new Set<() => void>()
  private state: DraftState = { text: '', status: 'idle', hydrated: false, recovered: false,
    revision: null, conflict: null, storageWarning: '' }

  constructor(readonly userId: number, readonly promptId: number, private transport: DraftTransport) {
    this.key = draftBackupKey(userId, promptId)
  }

  snapshot = () => this.state
  subscribe = (listener: () => void) => {
    this.listeners.add(listener)
    return () => { this.listeners.delete(listener) }
  }

  /** Cancela o que ainda não saiu e ignora o que chegar depois. */
  dispose = () => {
    this.active = false
    if (this.timer !== null) window.clearTimeout(this.timer)
    this.timer = null
  }

  private publish(patch: Partial<DraftState> = {}) {
    this.state = { ...this.state, text: this.text, revision: this.revision, ...patch }
    this.listeners.forEach((listener) => listener())
  }

  /** Lê a conta e o espelho local; o conflito é decidido aqui, antes de salvar. */
  hydrate = async () => {
    let remote: WritingDraft | null = null
    let failed = false
    try {
      remote = await this.transport.read()
    } catch {
      failed = true
    }
    if (!this.active) return
    const stored = readLocal(this.key)
    const backup = stored.ok ? stored.value : null
    this.mirrored = backup
    const metadata = readLocal(`${this.key}:revision`)
    const base = metadata.ok && metadata.value !== null ? Number(metadata.value) : null
    this.revision = remote ? (remote.revision ?? 0) : null
    this.text = backup ?? remote?.text ?? ''
    this.queued = remote?.text ?? ''
    // Backup diferente da conta só é conflito quando ele não deriva da revisão
    // que a conta tem agora; senão seria um aviso a cada aba aberta.
    const divergent = backup !== null && remote !== null && backup !== remote.text
      && (base !== this.revision || base === null)
    this.publish({
      hydrated: true,
      recovered: backup !== null,
      conflict: divergent ? remote : null,
      storageWarning: stored.ok ? '' : `${stored.error} Pode existir um rascunho local mais recente.`,
      status: failed ? (backup !== null ? 'local' : 'unsaved') : 'idle',
    })
  }

  /** Espelha no dispositivo na hora e agenda o salvamento na conta. */
  change = (value: string) => {
    this.text = value
    const written = writeLocal(this.key, value)
    if (this.revision !== null) writeLocal(`${this.key}:revision`, String(this.revision))
    this.mirrored = written.ok ? value : null
    this.publish({
      status: written.ok ? 'local' : 'unsaved',
      storageWarning: written.ok ? '' : `${written.error} Copie o texto antes de sair.`,
    })
    if (this.state.conflict) return
    if (this.timer !== null) window.clearTimeout(this.timer)
    this.timer = window.setTimeout(() => {
      this.timer = null
      if (this.text === this.queued) return
      this.queued = this.text
      void this.save(this.text)
    }, DRAFT_SAVE_DELAY)
  }

  /** Enfileira o salvamento. Serial de propósito: dois PUT em paralelo brigariam pela revisão. */
  private save(value: string) {
    this.publish({ status: 'saving' })
    this.queue = this.queue
      .catch(() => undefined)
      .then(async () => {
        if (!this.active || this.state.conflict) return
        const expected = await this.confirmed(value)
        if (expected === null) return
        const saved = await this.transport.save({ text: value, expected_revision: expected })
        if (!this.active) return
        this.revision = saved.revision ?? 0
        this.settle(value)
      })
      .catch((error: unknown) => {
        if (!this.active) return
        if (error instanceof DraftConflict) {
          this.publish({ conflict: error.current, status: 'local' })
          return
        }
        if (this.text !== value) return
        // Uma falha não pode afirmar persistência: sem espelho local, o texto
        // está só nesta tela e o aluno precisa saber antes de fechar a página.
        this.queued = ''
        this.publish({ status: this.mirrored === value ? 'local' : 'unsaved' })
      })
    return this.queue
  }

  /** Sem revisão confirmada, lê a conta antes de escrever sobre ela. */
  private async confirmed(value: string): Promise<number | null> {
    if (this.revision !== null) return this.revision
    const remote = await this.transport.read()
    if (!this.active) return null
    if (remote.text !== value) {
      this.publish({ conflict: remote, status: 'local' })
      return null
    }
    this.revision = remote.revision ?? 0
    return this.revision
  }

  /** Limpa o espelho só quando ele é igual ao que a conta confirmou. */
  private settle(value: string) {
    if (this.text !== value) {
      // O próximo espelho deriva do save confirmado, não da revisão anterior.
      const stored = readLocal(this.key)
      if (stored.ok && stored.value === this.text) writeLocal(`${this.key}:revision`, String(this.revision))
      this.publish()
      return
    }
    const stored = readLocal(this.key)
    // Uma confirmação desta aba não apaga o texto diferente de outra.
    const removed = !stored.ok ? stored : stored.value !== value ? { ok: true as const } : removeLocal(this.key)
    if (removed.ok) this.mirrored = null
    if (stored.ok && stored.value === value) removeLocal(`${this.key}:revision`)
    this.publish({ status: 'saved', storageWarning: removed.ok ? '' : removed.error })
  }

  /** Envia agora o que ainda não foi aceito, sem esperar o temporizador.
   *
   * Serve para o fim de uma ação do aluno e para o reenvio explícito depois de
   * uma falha — nos dois casos a pergunta é a mesma: o que está na tela já foi
   * confirmado pela conta? Se não foi, vai agora.
   */
  flush = async () => {
    if (this.timer !== null) {
      window.clearTimeout(this.timer)
      this.timer = null
    }
    if (this.text !== this.queued && !this.state.conflict) {
      this.queued = this.text
      this.save(this.text)
    }
    await this.queue.catch(() => undefined)
  }

  /** Entra na mesma fila, depois de esvaziá-la.
   *
   * Sem o `flush` a versão correria com o autosave do mesmo texto: as duas
   * escrevem sobre a mesma revisão e a ordem seria o acaso do temporizador.
   * Assim a versão sempre nasce do rascunho já confirmado.
   */
  createVersion = async (): Promise<WritingRevision | null> => {
    if (!this.text.trim() || this.state.conflict) return null
    await this.flush()
    if (!this.active || this.state.conflict || this.revision === null) return null
    const value = this.text
    let created: WritingRevision | null = null
    this.queue = this.queue
      .catch(() => undefined)
      .then(async () => {
        const expected = this.revision
        if (!this.active || this.state.conflict || expected === null) return
        const version = await this.transport.createVersion({ text: value, expected_revision: expected })
        if (!this.active) return
        this.revision = version.draft_revision ?? this.revision
        created = version
        this.publish()
      })
      .catch((error: unknown) => {
        if (!this.active) return
        if (error instanceof DraftConflict) this.publish({ conflict: error.current })
        throw error
      })
    await this.queue
    return created
  }

  /** Escolha explícita do aluno; nada sobrescreve a conta antes dela. */
  resolve = (useRemote: boolean) => {
    const remote = this.state.conflict
    if (!remote) return
    this.revision = remote.revision ?? 0
    if (!useRemote) {
      this.publish({ conflict: null })
      this.queued = this.text
      void this.save(this.text)
      return
    }
    this.text = remote.text
    this.queued = remote.text
    const removed = removeLocal(this.key)
    if (removed.ok) this.mirrored = null
    removeLocal(`${this.key}:revision`)
    this.publish({ conflict: null, status: 'saved', storageWarning: removed.ok ? '' : removed.error })
  }
}
