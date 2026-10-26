import type { CourseCompletion } from '../../api/client'

/** Rótulos do fechamento do curso.
 *
 * Ficam juntos porque todos traduzem estado de servidor para o que o aluno lê,
 * e porque cada tela do fechamento usa mais de um deles.
 */
export function completionStatusLabel(status: CourseCompletion['progress']['status']): string {
  if (status === 'completed') return 'Aulas publicadas concluídas'
  if (status === 'in_progress') return 'Em andamento'
  return 'Ainda não iniciado'
}

export function levelLabel(level: string): string {
  const normalized = level.trim()
  return /^level\b/i.test(normalized) ? normalized : `Level ${normalized}`
}

export function courseStatusLabel(status: NonNullable<CourseCompletion['next_course']>['status']): string {
  if (status === 'published') return 'Disponível'
  if (status === 'planned') return 'Em preparação'
  return 'Arquivado'
}

export function skillStatusLabel(status: CourseCompletion['skills'][number]['status']): string {
  if (status === 'strong') return 'Consistente'
  if (status === 'steady') return 'Estável'
  if (status === 'developing') return 'Em desenvolvimento'
  return 'Dados insuficientes'
}
