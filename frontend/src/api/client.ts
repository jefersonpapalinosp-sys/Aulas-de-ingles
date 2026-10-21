import createClient, { type Middleware } from 'openapi-fetch'
import type { components } from './schema'
import { isRevisionRequired, markRevisionRequired } from './revisionRequired'
import { assertRevisionedWrite, type RevisionedPaths } from './revisionedWrites'
import { encerrarSessao, estadoIndisponivel, renovarSessao, sessionSnapshot } from './session'
export {
  onEstadoSessao, onSessaoPerdida, renovarSessao, setAccessToken,
  setSessionReadOnly, setSessionUser,
} from './session'

/**
 * Cliente tipado pelo contrato. Os tipos saem de `npm run gen:api`, que lê o
 * backend/openapi.json — nenhuma interface desta pasta é escrita à mão.
 * `RevisionedPaths` só aperta os corpos das escritas do cutover de 13/11/2026:
 * `expected_revision`/`operation_key`/`idempotency_key` deixam de ser opcionais.
 *
 * baseUrl vazio de propósito: o browser fala com /api na mesma origem e o
 * proxy do Vite leva até a API. Sem CORS, e o cookie httpOnly do refresh
 * viaja sem configuração extra.
 */
export const api = createClient<RevisionedPaths>({ baseUrl: '', credentials: 'same-origin' })

type Pedido = ReturnType<typeof sessionSnapshot> & { copia: Request | null }
const pedidos = new WeakMap<Request, Pedido>()
const rotaAuth = (request: Request) => new URL(request.url).pathname.startsWith('/api/auth/')

function indisponivel(): Response {
  // Não devolver o 401 inicial como se a revogação estivesse confirmada.
  // Mantém o contrato HTTP usado pelas filas: 503 interrompe sem descartar.
  return new Response(JSON.stringify({ code: 'service_unavailable', detail: 'Não foi possível confirmar sua sessão agora. Tente novamente.' }), {
    status: 503,
    headers: { 'Content-Type': 'application/json', 'X-Session-State': estadoIndisponivel(), 'X-Error-Code': 'service_unavailable' },
  })
}

function preparar(request: Request, reproduzivel: boolean): Pedido {
  const snapshot = sessionSnapshot()
  if (snapshot.perfilNaoConfirmado && !rotaAuth(request)) request.headers.delete('Authorization')
  else if (snapshot.token) request.headers.set('Authorization', `Bearer ${snapshot.token}`)
  return { ...snapshot, copia: reproduzivel && !rotaAuth(request) ? request.clone() : null }
}

function envioBloqueado(request: Request, pedido: Pedido): boolean {
  // GET público ainda pode alcançar o cache textual do service worker, mas
  // sem token e sem renovar automaticamente a partir de um perfil local.
  return pedido.perfilNaoConfirmado && !rotaAuth(request) && request.method !== 'GET'
}

function conferirGeracao(request: Request, pedido: Pedido): void {
  request.signal.throwIfAborted()
  if (sessionSnapshot().geracao !== pedido.geracao) {
    throw new DOMException('A sessão mudou. Esta operação não será reenviada em outra conta.', 'AbortError')
  }
}

async function receber(request: Request, response: Response, pedido: Pedido,
  enviar: (request: Request) => Promise<Response>): Promise<Response> {
  const final = await receberSessao(request, response, pedido, enviar)
  // 428 após o cutover: o cliente ficou para trás. A interface pede atualização
  // com confirmação; nada local é descartado e a resposta segue para o chamador.
  if (isRevisionRequired(final)) markRevisionRequired()
  return final
}

async function receberSessao(request: Request, response: Response, pedido: Pedido,
  enviar: (request: Request) => Promise<Response>): Promise<Response> {
  if (rotaAuth(request)) return response
  conferirGeracao(request, pedido)
  if (response.status !== 401 || pedido.perfilNaoConfirmado) return response
  // Streams não são copiados: não há garantia de reprodução nem buffer limitado.
  if (!pedido.copia) return response
  const atual = sessionSnapshot()
  if (atual.perfilNaoConfirmado) return indisponivel()
  const resultado = atual.token && atual.token !== pedido.token
    ? { estado: 'valida' as const, token: atual.token }
    : await renovarSessao()
  if (resultado.estado === 'expirada') return response
  conferirGeracao(request, pedido)
  if (resultado.estado !== 'valida') return indisponivel()
  pedido.copia.headers.set('Authorization', `Bearer ${resultado.token}`)
  const repetida = await enviar(pedido.copia)
  conferirGeracao(request, pedido)
  // Não há recursão: uma única repetição, preservando corpo e chave idempotente.
  if (repetida.status === 401 && sessionSnapshot().token === resultado.token) {
    encerrarSessao(pedido.geracao)
  }
  return repetida
}

/** Áudio, exportação e JSON usam as mesmas regras de sessão e repetição. */
export async function authenticatedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const url = new URL(path, window.location.href)
  if (url.origin !== window.location.origin || !url.pathname.startsWith('/api/')) {
    throw new Error('O transporte autenticado aceita apenas a API desta aplicação.')
  }
  const request = new Request(url, { ...init, credentials: 'same-origin' })
  const reproduzivel = !(typeof ReadableStream !== 'undefined' && init.body instanceof ReadableStream)
  if (reproduzivel) await assertRevisionedWrite(request)
  const pedido = preparar(request, reproduzivel)
  if (envioBloqueado(request, pedido)) return indisponivel()
  return receber(request, await fetch(request), pedido, (retry) => fetch(retry))
}

/** Exportado para o teste montar um cliente com base absoluta. */
export const autenticacao: Middleware = {
  async onRequest({ request }) {
    const json = request.headers.get('Content-Type')?.includes('application/json') ?? false
    if (json) await assertRevisionedWrite(request)
    const pedido = preparar(request, request.body === null || json)
    if (envioBloqueado(request, pedido)) return indisponivel()
    pedidos.set(request, pedido)
    return request
  },
  onError({ request }) {
    pedidos.delete(request)
  },
  async onResponse({ request, response, options }) {
    const pedido = pedidos.get(request)
    pedidos.delete(request)
    return pedido ? receber(request, response, pedido, options.fetch) : response
  },
}

api.use(autenticacao)

export type LessonSummary = components['schemas']['LessonSummaryOut']
export type LessonDetail = components['schemas']['LessonDetailOut']
export type CourseSummary = components['schemas']['CourseSummaryOut']
export type CourseUnit = components['schemas']['CourseUnitOut']
export type CourseCurriculum = components['schemas']['CourseCurriculumOut']
export type CourseReview = components['schemas']['CourseReviewDetailOut']
export type CourseReviewAttempt = components['schemas']['CourseReviewAttemptOut']
export type CourseReviewAttemptInput = components['schemas']['CourseReviewAttemptIn']
export type CourseCompletion = components['schemas']['CourseCompletionOut']
export type GrammarBlock = components['schemas']['GrammarBlockOut']
export type Phrase = components['schemas']['PhraseOut']
export type VocabItem = components['schemas']['VocabItemOut']
export type PronunciationNote = components['schemas']['PronunciationNoteOut']
export type LessonMedia = components['schemas']['LessonMediaOut']
export type TranscriptCue = components['schemas']['TranscriptCueOut']
export type TranscriptLine = components['schemas']['TranscriptLineOut']
export type MediaPosition = components['schemas']['MediaPositionOut']
export type WritingPrompt = components['schemas']['WritingPromptOut']
export type WritingDraft = components['schemas']['WritingDraftOut']
export type WritingRevision = components['schemas']['WritingRevisionOut']
export type WritingRevisionPage = components['schemas']['WritingRevisionPageOut']
export type WritingFeedback = components['schemas']['WritingFeedbackOut']
export type WritingHistoryItem = components['schemas']['WritingHistoryItemOut']
export type WritingHistorySummary = components['schemas']['WritingHistorySummaryOut']
export type WritingHistoryPage = components['schemas']['WritingHistoryPageOut']
export type WritingFeedbackPage = components['schemas']['WritingFeedbackPageOut']
export type SpeakingAttempt = components['schemas']['SpeakingAttemptOut']
export type SpeakingAttemptPage = components['schemas']['SpeakingAttemptPageOut']
export type TranscriptionJob = components['schemas']['TranscriptionJobOut']
export type AssistStatus = components['schemas']['AssistStatusOut']
export type NotebookEntry = components['schemas']['NotebookEntryOut']
export type NotebookPage = components['schemas']['NotebookPageOut']
export type NotebookKind = components['schemas']['NotebookEntryOut']['kind']
export type HistoricalContent = components['schemas']['HistoricalContentOut']
export type HistoricalEvidence = components['schemas']['HistoricalEvidenceSummaryOut']
export type HistoricalEvidenceKind = HistoricalEvidence['evidence_kind']
export type Exercise = components['schemas']['ExerciseOut']
export type ExerciseWithLesson = components['schemas']['ExerciseWithLessonOut']
export type AttemptFeedback = components['schemas']['AttemptFeedbackOut']
export type ExerciseHint = components['schemas']['ExerciseHintOut']
export type Progress = components['schemas']['ProgressOut']
export type StudySession = components['schemas']['StudySessionOut']
export type StudySessionInput = components['schemas']['StudySessionIn']
export type StudyPlan = components['schemas']['StudyPlanOut']
export type StudyPlanInput = components['schemas']['StudyPlanIn']
export type Today = components['schemas']['TodayOut']
export type SkillSummary = components['schemas']['SkillSummaryOut']
export type ReviewItem = components['schemas']['CardOut']
export type ReviewItemPage = components['schemas']['ReviewItemPageOut']
export type ReviewItemType = components['schemas']['CardOut']['item_type']
export type Health = components['schemas']['HealthOut']
