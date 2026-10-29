import { clearVoiceDraft, retainVoiceDraft, takeVoiceDraft } from './voiceDraft'

/** Motor do envio da gravação.
 *
 * O envio é em dois passos — cria a tentativa, depois manda o áudio — e isso é
 * o que exige um motor: se a resposta do primeiro passo se perde, reenviar não
 * pode criar uma segunda tentativa, e se a sessão trocar no meio o áudio não
 * pode ir para a conta errada. A gravação fica guardada na memória desta aba
 * enquanto o envio não confirma, para que uma falha de rede não a apague.
 */

export type SelfRating = 'repeat' | 'almost' | 'confident'

export type SpeakingUploadState = {
  saving: boolean
  /** Esta gravação já está confirmada na conta. */
  saved: boolean
  /** A tentativa existe na conta e espera o áudio. */
  pending: boolean
}

export type RecoveredRecording = { blob: Blob; duration: number; pending: boolean }

export type SpeakingUploadRequest = {
  key: string
  cueId: number
  blob: Blob
  duration: number
  rating: SelfRating | null
}

export type SpeakingSession = {
  usuarioId: number | null
  token: string | null
  perfilNaoConfirmado: boolean
  geracao: number
}

export type SpeakingUploadTransport = {
  /** `id` da tentativa criada, ou o status que explica a recusa. */
  createAttempt: (
    body: { cue_id: number; duration_ms: number; self_rating: SelfRating | null; consent: true },
    signal: AbortSignal,
  ) => Promise<{ id: number } | { status?: number }>
  putAudio: (attemptId: number, blob: Blob, signal: AbortSignal) => Promise<{ ok: boolean; status: number }>
  session: () => SpeakingSession
}

export function uploadError(status?: number): string {
  if (status === 413) return 'Áudio maior que o limite permitido. Grave um trecho mais curto.'
  if (status === 415) return 'Formato não aceito pelo servidor. Use outro navegador para gravar.'
  if (status === 422) return 'Áudio inválido ou com duração real acima do limite. Baixe sua gravação e grave um trecho mais curto.'
  if (status === 401 || status === 403) return 'Sua sessão precisa ser confirmada antes de tentar novamente.'
  if (status === 409) return 'Esta tentativa já contém outro áudio; nada foi sobrescrito.'
  if (status === 408) return 'O envio demorou demais. Tente novamente.'
  return 'Não foi possível confirmar o envio. Tente novamente.'
}

const SESSION_CHANGED = 'A sessão mudou. Confirme a mesma conta antes de reenviar.'

export class SpeakingUpload {
  private listeners = new Set<() => void>()
  private state: SpeakingUploadState = { saving: false, saved: false, pending: false }
  private attemptId: number | null = null
  private controller: AbortController | null = null
  /** Identidade do envio corrente. Sobe a cada aborto ou troca de frase. */
  private generation = 0
  private recovered: { key: string; blob: Blob; duration: number; attemptId: number | null } | null = null

  constructor(readonly userId: number, private transport: SpeakingUploadTransport) {}

  snapshot = () => this.state
  subscribe = (listener: () => void) => {
    this.listeners.add(listener)
    return () => { this.listeners.delete(listener) }
  }

  private publish(patch: Partial<SpeakingUploadState>) {
    this.state = { ...this.state, ...patch }
    this.listeners.forEach((listener) => listener())
  }

  private abort() {
    this.generation += 1
    this.controller?.abort()
    this.controller = null
    this.attemptId = null
  }

  /** Troca de frase ou desmonte: nada em voo segue valendo. */
  reset = () => {
    this.abort()
    this.publish({ saving: false, saved: false, pending: false })
  }

  dispose = () => { this.abort() }

  /** Retoma a gravação guardada nesta aba para esta frase, se houver.
   *
   * A gravação recuperada é lembrada aqui porque o efeito que a pede pode
   * rodar duas vezes (StrictMode) — e a segunda não pode achar que não havia
   * nada.
   */
  recover = (key: string): RecoveredRecording | null => {
    const found = takeVoiceDraft(key) ?? (this.recovered?.key === key ? this.recovered : null)
    this.recovered = found
    if (!found) return null
    this.attemptId = found.attemptId
    this.publish({ pending: found.attemptId !== null, saved: false, saving: false })
    return { blob: found.blob, duration: found.duration, pending: found.attemptId !== null }
  }

  /** Descarte explícito do aluno: a gravação sai da memória desta aba. */
  discard = (key: string) => {
    this.recovered = null
    clearVoiceDraft(key)
    this.reset()
  }

  /** Cria a tentativa (se ainda não existe) e manda o áudio.
   *
   * A mensagem devolvida é a fala da tela: vazia quer dizer que esta resposta
   * já não é a corrente — outra frase foi escolhida, ou o envio foi abortado —
   * e nada deve ser dito ao aluno.
   */
  save = async (request: SpeakingUploadRequest): Promise<{ ok: boolean; message: string }> => {
    if (this.state.saving || this.controller) return { ok: false, message: '' }
    const session = this.transport.session()
    if (session.usuarioId !== this.userId || !session.token || session.perfilNaoConfirmado) {
      return { ok: false, message: 'Confirme a sessão da mesma conta para tentar novamente. O áudio continua nesta tela.' }
    }
    // Guardada antes de qualquer rede: a partir daqui uma falha não pode
    // significar gravação perdida.
    const recovery = { key: request.key, blob: request.blob, duration: request.duration, attemptId: this.attemptId }
    retainVoiceDraft(recovery)
    const controller = new AbortController()
    this.controller = controller
    // A identidade é a geração, e não o controller: ele é anulado no `finally`
    // antes desta checagem, e comparar com ele faria todo envio bem-sucedido
    // parecer obsoleto.
    const generation = this.generation
    const current = () => !controller.signal.aborted && this.generation === generation
    const sameAccount = () => current()
      && this.transport.session().geracao === session.geracao
      && this.transport.session().usuarioId === this.userId
    this.publish({ saving: true })
    try {
      if (this.attemptId === null) {
        const created = await this.transport.createAttempt(
          { cue_id: request.cueId, duration_ms: request.duration, self_rating: request.rating, consent: true },
          controller.signal,
        )
        if (!('id' in created)) throw new Error(uploadError(created.status))
        // O id é anotado antes de olhar a sessão: a tentativa já existe na
        // conta, e esquecê-la faria o reenvio criar uma segunda.
        this.attemptId = created.id
        recovery.attemptId = created.id
        this.publish({ pending: true })
        if (!sameAccount()) throw new Error(SESSION_CHANGED)
      }
      const upload = await this.transport.putAudio(this.attemptId, request.blob, controller.signal)
      if (!sameAccount()) throw new Error(SESSION_CHANGED)
      if (!upload.ok) throw new Error(uploadError(upload.status))
      this.publish({ saved: true })
      return { ok: true, message: 'Gravação salva na sua conta. Você pode ouvi-la ou excluí-la abaixo.' }
    } catch (error) {
      // Falha de rede pode ser só perda da resposta: não apagar uma gravação
      // que talvez já esteja confirmada na conta.
      if (!current()) return { ok: false, message: '' }
      const motivo = error instanceof Error && error.message !== 'Failed to fetch'
        ? error.message
        : 'Falha de conexão. Tente novamente.'
      return { ok: false, message: `${motivo} O áudio continua nesta tela; você pode baixá-lo.` }
    } finally {
      // Sessão perdida mantém a gravação guardada: o aluno tem cinco minutos
      // para entrar na mesma conta e voltar a este trecho.
      if (this.transport.session().usuarioId !== null) clearVoiceDraft(request.key, recovery)
      if (this.controller === controller) this.controller = null
      if (current()) this.publish({ saving: false })
    }
  }
}
