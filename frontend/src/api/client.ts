import createClient from 'openapi-fetch'
import type { components, paths } from './schema'

/**
 * Cliente tipado pelo contrato. Os tipos saem de `npm run gen:api`, que lê o
 * backend/openapi.json — nenhuma interface desta pasta é escrita à mão.
 *
 * baseUrl vazio de propósito: o browser fala com /api na mesma origem e o
 * proxy do Vite leva até a API. Sem CORS, e pronto para o cookie da S3.
 */
export const api = createClient<paths>({ baseUrl: '' })

export type LessonSummary = components['schemas']['LessonSummaryOut']
export type LessonDetail = components['schemas']['LessonDetailOut']
export type GrammarBlock = components['schemas']['GrammarBlockOut']
export type Phrase = components['schemas']['PhraseOut']
export type VocabItem = components['schemas']['VocabItemOut']
export type PronunciationNote = components['schemas']['PronunciationNoteOut']
export type Exercise = components['schemas']['ExerciseOut']
export type ExerciseWithLesson = components['schemas']['ExerciseWithLessonOut']
export type Health = components['schemas']['HealthOut']
