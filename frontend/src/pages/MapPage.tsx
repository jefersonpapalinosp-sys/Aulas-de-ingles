import { useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { StudyPlan, StudyPlanInput } from '../api/client'
import { useSaveStudyPlan, useSkills, useToday } from '../api/dashboard'
import { useProgress } from '../api/progress'
import { useCourseCurriculum } from '../api/queries'
import { Carregando, Erro } from '../components/States'
import { lessonProgressKey } from '../features/curriculum/curriculum'
import {
  canonicalizeLegacyHref,
  coursePath,
  courseReviewPath,
  DEFAULT_COURSE_SLUG,
  lessonPath,
  unitPath,
} from '../routing/courseRoutes'

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
      {save.isSuccess && (
        <p className="today-save ok" role="status">
          Plano salvo.
        </p>
      )}
      {save.isError && (
        <p className="today-save erro" role="alert">
          Não foi possível salvar.
        </p>
      )}
    </form>
  )
}

function TodayPanel() {
  const today = useToday()
  const skills = useSkills()

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
          <h2>{recommendation.title}</h2>
          <p>{recommendation.reason}</p>
        </div>
        <Link className="btn" to={canonicalizeLegacyHref(recommendation.href)}>
          Estudar agora
        </Link>
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
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}

export function MapPage({ showToday = false }: { showToday?: boolean }) {
  const params = useParams()
  const courseSlug = params.courseSlug ?? DEFAULT_COURSE_SLUG
  const unitSlug = params.unitSlug
  const curriculum = useCourseCurriculum(courseSlug)
  const progress = useProgress(courseSlug)

  if (curriculum.isPending) return <Carregando oque="o mapa do curso" />
  if (curriculum.error) {
    return (
      <Erro erro={curriculum.error} aoTentarDeNovo={() => void curriculum.refetch()} />
    )
  }

  const studied = new Set(
    progress.data?.lessons
      .filter((lesson) => lesson.studied)
      .map((lesson) => lessonProgressKey(lesson.course_slug, lesson.lesson_number)) ?? [],
  )
  const selectedUnit = unitSlug
    ? curriculum.data.units.find((unit) => unit.slug === unitSlug)
    : undefined

  if (unitSlug && !selectedUnit) {
    return (
      <div className="estado-erro" role="alert">
        <p>Esta unidade não existe neste curso.</p>
        <Link className="btn ghost" to={coursePath(courseSlug)}>
          Ver unidades
        </Link>
      </div>
    )
  }

  return (
    <>
      {showToday && <TodayPanel />}
      <section
        className={showToday ? 'map-section course-map' : 'course-map'}
        aria-labelledby="map-title"
      >
        <p className="eyebrow">
          {curriculum.data.course.title} · {curriculum.data.course.proficiency_label} ·{' '}
          {curriculum.data.course.provider}
        </p>
        <div className="course-map-title">
          <div>
            <h1 id="map-title">
              {selectedUnit ? selectedUnit.title : 'Mapa do curso'}
            </h1>
            <p className="lead">
              {selectedUnit
                ? `${selectedUnit.published_lessons} aulas disponíveis${selectedUnit.review ? ' e um checkpoint de consolidação' : ''} nesta unidade.`
                : 'Abra uma unidade para ver uma lista curta de aulas e continuar sem percorrer o curso inteiro.'}
            </p>
          </div>
          {selectedUnit && (
            <Link to={coursePath(courseSlug)} className="btn ghost">
              Todas as unidades
            </Link>
          )}
        </div>

        <div className="unit-card-grid">
          {curriculum.data.units.map((unit) => {
            const completed = unit.lessons.filter((lesson) =>
              studied.has(lessonProgressKey(courseSlug, lesson.number)),
            ).length
            const state =
              unit.published_lessons === 0
                ? unit.status === 'planned'
                  ? 'Em preparação'
                  : 'Sem aulas publicadas'
                : completed === 0
                ? 'Não iniciada'
                : completed === unit.lessons.length
                  ? unit.review
                    ? 'Aulas concluídas · checkpoint disponível'
                    : 'Concluída'
                  : 'Em andamento'
            return (
              <Link
                className={`unit-card${unit.slug === unitSlug ? ' active' : ''}`}
                key={unit.id}
                to={unitPath(courseSlug, unit.slug)}
                aria-current={unit.slug === unitSlug ? 'page' : undefined}
              >
                <span>
                  <strong>{unit.title}</strong>
                  <small>
                    Aulas {unit.lesson_start}–{unit.lesson_end}
                    {unit.review ? ' · checkpoint' : ''}
                  </small>
                </span>
                <span>
                  <small>{state}</small>
                  <strong>
                    {completed}/{unit.lessons.length}{' '}
                    {unit.lessons.length === 1 ? 'aula' : 'aulas'}
                  </strong>
                </span>
              </Link>
            )
          })}
        </div>

        {selectedUnit && (
          <div className="arc course-unit-lessons">
            <div className="ahead">
              <span>Aula</span>
              <span>Título</span>
              <span>Foco gramatical</span>
              <span>Estado</span>
            </div>
            {selectedUnit.lessons.map((lesson) => {
              const isStudied = studied.has(lessonProgressKey(courseSlug, lesson.number))
              return (
                <Link
                  className="arow"
                  key={lesson.id}
                  to={lessonPath(courseSlug, lesson.number)}
                >
                  <span className="an">{lesson.number}</span>
                  <span className="at">{lesson.title}</span>
                  <span className="ag">{lesson.grammar_tag}</span>
                  <span className={`ap ${isStudied ? 'is-studied' : ''}`}>
                    {isStudied ? 'Estudada' : 'Pendente'}
                  </span>
                </Link>
              )
            })}
            {selectedUnit.review && (
              <Link
                className="arow checkpoint-map-row"
                to={courseReviewPath(courseSlug, selectedUnit.slug)}
              >
                <span className="an" aria-hidden="true">CP</span>
                <span className="at">{selectedUnit.review.title}</span>
                <span className="ag">
                  {selectedUnit.review.question_count} questões · cerca de{' '}
                  {selectedUnit.review.estimated_minutes} min
                </span>
                <span className="ap">Abrir</span>
              </Link>
            )}
          </div>
        )}
      </section>
    </>
  )
}
