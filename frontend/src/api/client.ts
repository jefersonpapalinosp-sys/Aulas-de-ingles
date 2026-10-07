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
export type Exercise = components['schemas']['ExerciseOut']
export type ExerciseWithLesson = components['schemas']['ExerciseWithLessonOut']
export type Progress = components['schemas']['ProgressOut']
export type Health = components['schemas']['HealthOut']
