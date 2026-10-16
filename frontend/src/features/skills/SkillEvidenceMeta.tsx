import type { SkillSummary } from '../../api/client'

const SOURCE_LABELS: Record<string, string> = {
  exercise_attempt: 'correção objetiva de exercício',
  writing_feedback: 'rubrica automática de escrita',
  speaking_attempt: 'autoavaliação oral',
}

function dateLabel(value: string): string {
  return new Intl.DateTimeFormat('pt-BR', { dateStyle: 'medium' }).format(new Date(value))
}

export function SkillEvidenceMeta({ skill }: { skill: SkillSummary }) {
  if (skill.samples === 0 || !skill.period_start || !skill.period_end) {
    return <p className="skill-evidence-meta">Nenhuma evidência registrada neste recorte.</p>
  }
  const start = dateLabel(skill.period_start)
  const end = dateLabel(skill.period_end)
  const sources = skill.sources
    .map((source) => `${SOURCE_LABELS[source.source_type] ?? source.source_type} (${source.samples})`)
    .join(', ')
  return (
    <p className="skill-evidence-meta">
      Origem: {sources}. Período: {start === end ? start : `${start} a ${end}`}.
      {' '}Amostra: {skill.samples}; tendência exibida a partir de {skill.minimum_samples}.
    </p>
  )
}
