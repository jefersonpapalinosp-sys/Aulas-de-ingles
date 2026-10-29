import type { CourseCurriculum, LessonSummary } from '../../api/client'

type Unidade = CourseCurriculum['units'][number]

/** O que a barra do celular diz que o aluno está vendo.
 *
 * Do mais específico para o mais geral: aula, checkpoint, unidade, curso. A
 * barra é o único rótulo de contexto nessa largura de tela — cair direto em
 * "Escolher aula" faria o aluno perder de vista onde está.
 */
export function trailLabel({
  levelLabel, lesson, checkpoint, unit, courseTitle,
}: {
  levelLabel: string
  lesson?: LessonSummary
  checkpoint?: Unidade['review']
  unit?: Unidade
  courseTitle?: string
}): string {
  if (lesson) return `${levelLabel} · Aula ${lesson.number} · ${lesson.title}`
  if (checkpoint) return `${levelLabel} · ${checkpoint.title}`
  if (unit) {
    const preparo = unit.published_lessons === 0 ? ' · Em preparação' : ''
    return `${levelLabel} · ${unit.title}${preparo}`
  }
  return courseTitle ?? 'Escolher aula'
}
