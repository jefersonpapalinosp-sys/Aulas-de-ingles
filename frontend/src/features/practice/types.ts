import type { components } from '../../api/schema'

type Schemas = components['schemas']

export type PracticeMode = Schemas['PracticeSessionCreateIn']['mode']
export type PracticeActivityType = NonNullable<
  Schemas['PracticeSessionCreateIn']['activity_type']
>
export type PracticeSkill = NonNullable<Schemas['PracticeSessionCreateIn']['skill']>
export type PracticeObjective = NonNullable<Schemas['PracticeSessionCreateIn']['objective']>
export type PracticeStatus = Schemas['PracticeSessionOut']['status']
export type PracticeItemOutcome = Schemas['PracticeSessionItemOut']['outcome']

export type PracticeFilters = {
  activityType?: PracticeActivityType
  skill?: PracticeSkill
  objective?: PracticeObjective
}

export type PracticeSummary = Schemas['PracticeSummaryOut']
export type PracticeSessionItem = Schemas['PracticeSessionItemOut']
export type PracticeSession = Schemas['PracticeSessionOut']
export type CreatePracticeSessionInput = Schemas['PracticeSessionCreateIn']

export type ExerciseActivityEvent =
  | {
      type: 'attempt'
      exerciseId: number
      status: 'correct' | 'incorrect' | 'queued'
      idempotencyKey: string
      correct: boolean | null
    }
  | { type: 'hint'; exerciseId: number; level: number }
  | { type: 'reveal'; exerciseId: number }

export const PRACTICE_MODE_LABELS: Record<PracticeMode, string> = {
  guided: 'Prática guiada',
  quick: 'Desafio rápido',
  mistakes: 'Repetir meus erros',
}

export const PRACTICE_OBJECTIVE_LABELS: Record<PracticeObjective, string> = {
  recognize: 'Reconhecer',
  apply: 'Aplicar',
  correct: 'Corrigir',
  produce: 'Produzir',
  listen: 'Ouvir',
}

export const ACTIVITY_TYPE_LABELS: Record<string, string> = {
  gap_fill: 'Completar lacunas',
  multiple_choice: 'Múltipla escolha',
  transformation: 'Transformação e correção',
  reorder: 'Ordenar palavras',
  dictation: 'Ditado',
  classification: 'Classificação',
}

export const SKILL_LABELS: Record<string, string> = {
  grammar: 'Gramática',
  listening: 'Listening',
}
