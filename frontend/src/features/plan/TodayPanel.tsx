import { Link } from 'react-router-dom'
import { useSkills, useToday } from '../../api/dashboard'
import { Carregando, Erro } from '../../components/States'
import { SkillEvidenceMeta } from '../skills/SkillEvidenceMeta'
import { canonicalizeLegacyHref, courseLevelLabel } from '../../routing/courseRoutes'
import { PlanEditor } from './PlanEditor'

export function TodayPanel({
  courseSlug,
  unitSlug,
}: {
  courseSlug: string
  unitSlug?: string
}) {
  const today = useToday(courseSlug)
  const skills = useSkills(courseSlug, unitSlug)
  const courseLevel = courseLevelLabel(courseSlug)

  if (today.isPending || skills.isPending) return <Carregando oque="seu painel de hoje" />
  if (today.error) {
    return <Erro erro={today.error} aoTentarDeNovo={() => void today.refetch()} />
  }
  if (skills.error) {
    return <Erro erro={skills.error} aoTentarDeNovo={() => void skills.refetch()} />
  }

  const recommendation = today.data.recommendation
  const progress = Math.min(
    100,
    Math.round(
      (today.data.recorded_minutes_this_week / today.data.plan.weekly_minutes) * 100,
    ),
  )

  return (
    <section className="today" aria-labelledby="today-title">
      <div className="today-title-row">
        <div>
          <p className="eyebrow">Seu estudo agora</p>
          <h1 id="today-title">Hoje</h1>
        </div>
        <div className="today-week" aria-label={`${progress}% da meta semanal registrada`}>
          <strong>{today.data.recorded_minutes_this_week} min</strong>
          <span>de {today.data.plan.weekly_minutes} min nesta semana</span>
          <small>Tempo ativo desde segunda-feira · {today.data.plan.timezone ?? 'UTC'}</small>
          <div>
            <i style={{ width: `${progress}%` }} />
          </div>
        </div>
      </div>

      <article className="today-recommendation">
        <div>
          <p className="eyebrow">
            Próxima atividade · cerca de {recommendation.estimated_minutes} min
          </p>
          <h2>
            {recommendation.lesson_number
              ? `${courseLevel} · ${recommendation.title}`
              : recommendation.title}
          </h2>
          <p>{recommendation.reason}</p>
        </div>
        <Link className="btn" to={canonicalizeLegacyHref(recommendation.href)}>
          Estudar agora
        </Link>
      </article>

      {today.data.recent_session && (
        <p className="today-resume">
          Última sessão:{' '}
          <strong>
            {courseLevel} · Aula {today.data.recent_session.lesson_number}
          </strong>{' '}
          ·{' '}
          {today.data.recent_session.completed_steps}/5 etapas ·{' '}
          {today.data.recent_session.total_minutes} min ativos
          {(today.data.recent_session.legacy_minutes ?? 0) > 0 && <> · {today.data.recent_session.legacy_minutes} min históricos estimados (fora da meta semanal)</>}
        </p>
      )}

      <div className="today-grid">
        <PlanEditor plan={today.data.plan} />
        <div className="today-skills">
          <div className="today-section-head">
            <div>
              <p className="eyebrow">Competências</p>
              <h2>Evidências do seu estudo</h2>
            </div>
          </div>
          <ul>
            {skills.data.map((skill) => (
              <li key={skill.skill}>
                <div>
                  <strong>{skill.label}</strong>
                  <small>
                    {skill.samples} {skill.samples === 1 ? 'evidência' : 'evidências'}
                  </small>
                </div>
                {skill.score_percent === null ? (
                  <span className="skill-insufficient">
                    Dados insuficientes ({skill.samples}/3)
                  </span>
                ) : (
                  <span className={`skill-score ${skill.status}`}>
                    {skill.score_percent}%
                  </span>
                )}
                {skill.fragile_topics.length > 0 && (
                  <p>Tópico para reforçar: {skill.fragile_topics.join(', ')}</p>
                )}
                <SkillEvidenceMeta skill={skill} />
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}
