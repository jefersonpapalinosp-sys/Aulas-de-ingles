import createClient, { type Middleware } from 'openapi-fetch'
import type { components, paths } from './schema'

/**
 * Cliente tipado pelo contrato. Os tipos saem de `npm run gen:api`, que lê o
 * backend/openapi.json — nenhuma interface desta pasta é escrita à mão.
 *
 * baseUrl vazio de propósito: o browser fala com /api na mesma origem e o
 * proxy do Vite leva até a API. Sem CORS, e o cookie httpOnly do refresh
 * viaja sem configuração extra.
 */
export const api = createClient<paths>({ baseUrl: '', credentials: 'same-origin' })

/**
 * O access token mora aqui, em memória do módulo — não em localStorage.
 * O que o JavaScript lê, um XSS também lê; o token some ao recarregar a
 * página e volta pelo /refresh, que usa o cookie httpOnly.
 */
let accessToken: string | null = null

export function setAccessToken(token: string | null): void {
  accessToken = token
}

/** Faz downloads/uploads binários preservando o token mantido em memória. */
export function authenticatedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  return fetch(path, { ...init, headers, credentials: 'same-origin' })
}

/** Avisado quando o refresh falha e a sessão realmente acabou. */
let aoPerderSessao: (() => void) | null = null

export function onSessaoPerdida(callback: (() => void) | null): void {
  aoPerderSessao = callback
}

/**
 * Renova o access token, no máximo uma vez por vez.
 *
 * Várias requisições podem levar 401 ao mesmo tempo — uma tela de aula
 * dispara várias. Sem este single-flight, cada uma chamaria /refresh, e como
 * o refresh **rotaciona** (usar um revoga o anterior), a segunda chamada
 * invalidaria a sessão que a primeira acabou de renovar.
 */
let renovacaoEmCurso: Promise<string | null> | null = null

async function renovarToken(): Promise<string | null> {
  if (!renovacaoEmCurso) {
    renovacaoEmCurso = (async () => {
      try {
        const resposta = await fetch('/api/auth/refresh', {
          method: 'POST',
          credentials: 'same-origin',
        })
        if (!resposta.ok) return null
        const corpo = (await resposta.json()) as { access_token?: string }
        return corpo.access_token ?? null
      } catch {
        return null
      } finally {
        // Libera a próxima tentativa só depois que esta terminar.
        queueMicrotask(() => {
          renovacaoEmCurso = null
        })
      }
    })()
  }
  return renovacaoEmCurso
}

const CABECALHO_RETENTATIVA = 'X-Retry-After-Refresh'

/** Exportado para o teste montar um cliente com base absoluta. */
export const autenticacao: Middleware = {
  onRequest({ request }) {
    if (accessToken) request.headers.set('Authorization', `Bearer ${accessToken}`)
    return request
  },

  /**
   * O access token vive 15 minutos. Sem isto, depois desse prazo toda escrita
   * falhava com 401 e a interface continuava mostrando o usuário logado — o
   * progresso ficava só no dispositivo, com "sincronização pendente".
   */
  async onResponse({ request, response }) {
    if (response.status !== 401) return response
    // A própria rota de refresh não é retentada, e cada requisição só tenta
    // uma vez: sem essas duas guardas, um refresh inválido vira laço infinito.
    if (new URL(request.url).pathname.startsWith('/api/auth/')) return response
    if (request.headers.get(CABECALHO_RETENTATIVA)) return response

    const novo = await renovarToken()
    if (!novo) {
      accessToken = null
      aoPerderSessao?.()
      return response
    }
    accessToken = novo

    const retentativa = request.clone()
    retentativa.headers.set('Authorization', `Bearer ${novo}`)
    retentativa.headers.set(CABECALHO_RETENTATIVA, '1')
    return fetch(retentativa)
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
export type WritingFeedback = components['schemas']['WritingFeedbackOut']
export type WritingHistoryItem = components['schemas']['WritingHistoryItemOut']
export type SpeakingAttempt = components['schemas']['SpeakingAttemptOut']
export type TranscriptionJob = components['schemas']['TranscriptionJobOut']
export type AssistStatus = components['schemas']['AssistStatusOut']
export type NotebookEntry = components['schemas']['NotebookEntryOut']
export type NotebookKind = components['schemas']['NotebookEntryOut']['kind']
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
export type ReviewItemType = components['schemas']['CardOut']['item_type']
export type Health = components['schemas']['HealthOut']
