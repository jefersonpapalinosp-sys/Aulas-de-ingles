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

const autenticacao: Middleware = {
  onRequest({ request }) {
    if (accessToken) request.headers.set('Authorization', `Bearer ${accessToken}`)
    return request
  },
}

api.use(autenticacao)

export type LessonSummary = components['schemas']['LessonSummaryOut']
export type LessonDetail = components['schemas']['LessonDetailOut']
export type GrammarBlock = components['schemas']['GrammarBlockOut']
export type Phrase = components['schemas']['PhraseOut']
export type VocabItem = components['schemas']['VocabItemOut']
export type PronunciationNote = components['schemas']['PronunciationNoteOut']
export type LessonMedia = components['schemas']['LessonMediaOut']
export type TranscriptCue = components['schemas']['TranscriptCueOut']
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
