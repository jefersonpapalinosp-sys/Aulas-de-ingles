import type { Exercise } from '../../api/client'
import {
  ACTIVITY_TYPE_LABELS,
  SKILL_LABELS,
  type PracticeActivityType,
  type PracticeFilters,
  type PracticeObjective,
  type PracticeSession,
  type PracticeSkill,
} from './types'

export type PracticeOptions = {
  activityTypes: PracticeActivityType[]
  skills: PracticeSkill[]
  objectives: PracticeObjective[]
}

function unique(values: Array<string | null | undefined>): string[] {
  return [...new Set(values.filter((value): value is string => Boolean(value)))].sort()
}

/** Os filtros oferecidos saem do pack da aula, não de uma lista fixa.
 *
 * Oferecer uma modalidade que a aula não tem levaria o aluno a um recorte
 * vazio por culpa da interface.
 */
export function practiceOptions(exercises: Exercise[]): PracticeOptions {
  return {
    activityTypes: unique(exercises.map((exercise) => exercise.activity_type)) as PracticeActivityType[],
    skills: unique(exercises.map((exercise) => exercise.skill)) as PracticeSkill[],
    objectives: unique(exercises.map((exercise) => exercise.objective)) as PracticeObjective[],
  }
}

/** Recorte de uma sessão existente, para recomeçar com o mesmo filtro.
 *
 * Valor que não está no mapa de rótulos é descartado: ele viria de um conteúdo
 * mais novo que esta versão do aplicativo não sabe nomear.
 */
export function filtersFromSession(session: PracticeSession): PracticeFilters {
  const activityType = session.activity_type && session.activity_type in ACTIVITY_TYPE_LABELS
    ? (session.activity_type as PracticeActivityType)
    : undefined
  const skill = session.skill && session.skill in SKILL_LABELS
    ? (session.skill as PracticeSkill)
    : undefined
  return { activityType, skill, objective: session.objective ?? undefined }
}
