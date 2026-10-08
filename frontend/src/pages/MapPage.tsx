import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import type { StudyPlan, StudyPlanInput } from '../api/client'
import { useSaveStudyPlan, useSkills, useToday } from '../api/dashboard'
import { useLessons } from '../api/queries'
import { Carregando, Erro } from '../components/States'

const DAYS = [
  ['mon', 'Seg'],
  ['tue', 'Ter'],
  ['wed', 'Qua'],
  ['thu', 'Qui'],
  ['fri', 'Sex'],
  ['sat', 'Sáb'],
  ['sun', 'Dom'],
] as const

function PlanEditor({ plan }: { plan: StudyPlan }) {
  const save = useSaveStudyPlan()
  const [weeklyMinutes, setWeeklyMinutes] = useState(plan.weekly_minutes)
  const [preferredDays, setPreferredDays] = useState<string[]>(plan.preferred_days)
  const [goal, setGoal] = useState(plan.goal)

  function submit(event: FormEvent) {
    event.preventDefault()
    save.mutate({
      weekly_minutes: weeklyMinutes,
      preferred_days: preferredDays as StudyPlanInput['preferred_days'],
      goal,
    })
  }

  return (
    <form className="today-plan" onSubmit={submit}>
      <div className="today-section-head">
        <div>
          <p className="eyebrow">Plano semanal</p>
          <h2>Ritmo que cabe na rotina</h2>
        </div>
        <button className="btn ghost" disabled={save.isPending || preferredDays.length === 0}>
          {save.isPending ? 'Salvando…' : 'Salvar plano'}
        </button>
      </div>
      <label>
        Meta
        <input
          type="text"
          value={goal}
          maxLength={200}
          required
          onChange={(event) => setGoal(event.target.value)}
        />
      </label>
      <label>
        Minutos por semana
        <input
          className="today-minutes"
          type="number"
          min={30}
          max={600}
          step={15}
          value={weeklyMinutes}
          onChange={(event) => setWeeklyMinutes(Number(event.target.value))}
        />
      </label>
      <fieldset>
        <legend>Dias preferidos</legend>
        <div className="today-days">
          {DAYS.map(([value, label]) => (
            <label key={value}>
              <input
                type="checkbox"
                checked={preferredDays.includes(value)}
                onChange={(event) =>
                  setPreferredDays((current) =>
                    event.target.checked
                      ? [...current, value]
                      : current.filter((day) => day !== value),
                  )
                }
              />
              <span>{label}</span>
            </label>
          ))}
        </div>
      </fieldset>
      {save.isSuccess && <p className="today-save ok" role="status">Plano salvo.</p>}
      {save.isError && <p className="today-save erro" role="alert">Não foi possível salvar.</p>}
    </form>
  )
}

function TodayPanel() {
  const today = useToday()
  const skills = useSkills()

  if (today.isPending || skills.isPending) return <Carregando oque="seu painel de hoje" />
  if (today.error) return <Erro erro={today.error} aoTentarDeNovo={() => void today.refetch()} />
  if (skills.error) return <Erro erro={skills.error} aoTentarDeNovo={() => void skills.refetch()} />

  const recommendation = today.data.recommendation
  const progress = Math.min(
    100,
    Math.round((today.data.recorded_minutes_this_week / today.data.plan.weekly_minutes) * 100),
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
          <div><i style={{ width: `${progress}%` }} /></div>
        </div>
      </div>

      <article className="today-recommendation">
        <div>
          <p className="eyebrow">Próxima atividade · cerca de {recommendation.estimated_minutes} min</p>
          <h2>{recommendation.title}</h2>
          <p>{recommendation.reason}</p>
        </div>
        <Link className="btn" to={recommendation.href}>Estudar agora</Link>
      </article>

      {today.data.recent_session && (
        <p className="today-resume">
          Última sessão: <strong>Aula {today.data.recent_session.lesson_number}</strong> ·{' '}
          {today.data.recent_session.completed_steps}/5 etapas ·{' '}
          {today.data.recent_session.total_minutes} min registrados
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
                  <small>{skill.samples} {skill.samples === 1 ? 'evidência' : 'evidências'}</small>
                </div>
                {skill.score_percent === null ? (
                  <span className="skill-insufficient">Dados insuficientes ({skill.samples}/3)</span>
                ) : (
                  <span className={`skill-score ${skill.status}`}>{skill.score_percent}%</span>
                )}
                {skill.fragile_topics.length > 0 && (
                  <p>Tópico para reforçar: {skill.fragile_topics.join(', ')}</p>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}

export function MapPage() {
  const { data, isPending, error, refetch } = useLessons()

  if (isPending) return <Carregando oque="as aulas" />
  if (error) return <Erro erro={error} aoTentarDeNovo={() => void refetch()} />

  return (
    <>
      <TodayPanel />
      <section className="map-section" aria-labelledby="map-title">
      <p className="eyebrow">Let's Learn English · Level 1 · VOA Learning English</p>
      <h2 id="map-title" className="map-title">Mapa do bloco 31–40</h2>
      <p className="lead">
        Dez aulas que montam, em sequência, o sistema de comparação e o sistema de futuro do inglês.
        A 31 abre com o comparativo, a 38 fecha com o superlativo e a 40 estende tudo para os
        advérbios — vale estudar na ordem.
      </p>

      <div className="arc">
        <div className="ahead">
          <span>Aula</span>
          <span>Título</span>
          <span>Foco gramatical</span>
          <span>Série</span>
        </div>
        {data.map((a) => (
          <Link className="arow" key={a.number} to={`/aulas/${a.number}`}>
            <span className="an">{a.number}</span>
            <span className="at">{a.title}</span>
            <span className="ag">{a.grammar_tag}</span>
            <span className="ap">{a.story_note ?? '—'}</span>
          </Link>
        ))}
      </div>
      </section>
    </>
  )
}
