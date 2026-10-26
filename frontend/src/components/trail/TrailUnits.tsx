import { NavLink } from 'react-router-dom'
import type { CourseCurriculum, LessonSummary } from '../../api/client'
import { lessonProgressKey, matchesLessonSearch } from '../../features/curriculum/curriculum'
import { courseReviewPath, lessonPath } from '../../routing/courseRoutes'

/** Teto de aulas mostradas por unidade aberta.
 *
 * Sem teto, uma unidade de 40 aulas empurra o resto da trilha para fora da
 * tela. A janela segue a aula atual, e a contagem avisa que há mais.
 */
const MAX_VISIBLE_LESSONS = 12

function visibleWindow(lessons: LessonSummary[], activeLessonNumber?: number): LessonSummary[] {
  if (lessons.length <= MAX_VISIBLE_LESSONS) return lessons
  const activeIndex = lessons.findIndex((lesson) => lesson.number === activeLessonNumber)
  if (activeIndex < 0) return lessons.slice(0, MAX_VISIBLE_LESSONS)
  const start = Math.max(
    0,
    Math.min(activeIndex - Math.floor(MAX_VISIBLE_LESSONS / 2), lessons.length - MAX_VISIBLE_LESSONS),
  )
  return lessons.slice(start, start + MAX_VISIBLE_LESSONS)
}

function matchesReview(unit: CourseCurriculum['units'][number], query: string): boolean {
  return Boolean(unit.review && (!query.trim()
    || unit.review.title.toLocaleLowerCase('pt-BR').includes(query.trim().toLocaleLowerCase('pt-BR'))))
}

/** Unidades e aulas da trilha, com a busca já aplicada.
 *
 * Unidade em preparação aparece como texto, e não como botão: ela existe no
 * currículo e esconder isso faria o aluno achar que o curso termina antes.
 */
export function TrailUnits({
  idPrefix, curriculum, courseSlug, courseLevel, query, expandedUnit, activeUnitSlug,
  activeLessonNumber, studied, completionPending, activeLessonRef,
  onUnitToggle, onLessonDone, onNavigate,
}: {
  idPrefix: string
  curriculum?: CourseCurriculum
  courseSlug: string
  courseLevel: string
  query: string
  expandedUnit: string | null
  activeUnitSlug?: string
  activeLessonNumber?: number
  studied: Set<string>
  completionPending: boolean
  activeLessonRef?: React.RefObject<HTMLAnchorElement | null>
  onUnitToggle: (unitSlug: string) => void
  onLessonDone: (lesson: LessonSummary, studied: boolean) => void
  onNavigate?: () => void
}) {
  const semResultado = curriculum?.units.every((unit) =>
    unit.lessons.every((lesson) => !matchesLessonSearch(lesson, query)) && !matchesReview(unit, query))

  return (
    <div className="trail-scroll">
      <div className="trail-units">
        {curriculum?.units.map((unit) => {
          const matches = unit.lessons.filter((lesson) => matchesLessonSearch(lesson, query))
          const reviewMatches = matchesReview(unit, query)
          const unavailable = unit.status !== 'published' || unit.published_lessons === 0
          const isExpanded = !unavailable && expandedUnit === unit.slug
          const visible = visibleWindow(matches, activeLessonNumber)
          return (
            <section className="trail-unit" key={unit.id}>
              {unavailable ? (
                <div className="trail-unit-toggle" aria-disabled="true" aria-label={`${unit.title}: Em preparação`}>
                  <span aria-hidden="true">·</span>
                  <span>
                    <strong>{unit.title}</strong>
                    <small>
                      Em preparação · {unit.total_lessons}{' '}
                      {unit.total_lessons === 1 ? 'aula' : 'aulas'}
                    </small>
                  </span>
                </div>
              ) : (
                <button
                  type="button"
                  className="trail-unit-toggle"
                  aria-expanded={isExpanded}
                  aria-controls={`${idPrefix}-trail-unit-${unit.id}`}
                  onClick={() => onUnitToggle(unit.slug)}
                >
                  <span aria-hidden="true">{isExpanded ? '−' : '+'}</span>
                  <span>
                    <strong>{unit.title}</strong>
                    <small>
                      {unit.published_lessons} {unit.published_lessons === 1 ? 'aula' : 'aulas'}
                    </small>
                  </span>
                  {unit.slug === activeUnitSlug && <em>Atual</em>}
                </button>
              )}
              {isExpanded && (
                <ul
                  id={`${idPrefix}-trail-unit-${unit.id}`}
                  className="trail-lessons"
                  aria-label={`Itens de ${unit.title}`}
                >
                  {visible.map((lesson) => {
                    const isActive = lesson.number === activeLessonNumber
                    const isStudied = studied.has(lessonProgressKey(courseSlug, lesson.number))
                    return (
                      <li className="trail-lesson-row" key={lesson.id}>
                        <NavLink
                          ref={isActive ? activeLessonRef : undefined}
                          to={lessonPath(courseSlug, lesson.number)}
                          className="trail-lesson-link"
                          onClick={onNavigate}
                        >
                          <span>{lesson.number}</span>
                          <span>
                            <strong>{lesson.title}</strong>
                            <small>{lesson.grammar_tag}</small>
                          </span>
                        </NavLink>
                        <button
                          type="button"
                          className="trail-done"
                          aria-pressed={isStudied}
                          aria-label={`${isStudied ? 'Desmarcar' : 'Marcar'} ${courseLevel} · Aula ${lesson.number} como estudada`}
                          title={isStudied ? 'Estudada' : 'Marcar como estudada'}
                          disabled={completionPending}
                          onClick={() => onLessonDone(lesson, !isStudied)}
                        >
                          <span aria-hidden="true">{isStudied ? '✓' : '○'}</span>
                        </button>
                      </li>
                    )
                  })}
                  {matches.length > MAX_VISIBLE_LESSONS && (
                    <li className="trail-limit" role="status">
                      Mostrando {visible.length} de {matches.length}. Refine a busca para
                      encontrar outra aula.
                    </li>
                  )}
                  {reviewMatches && unit.review && (
                    <li className="trail-review-row">
                      <NavLink to={courseReviewPath(courseSlug, unit.slug)} onClick={onNavigate}>
                        <span aria-hidden="true">CP</span>
                        <span>
                          <strong>{unit.review.title}</strong>
                          <small>
                            {unit.review.question_count} questões ·{' '}
                            {unit.review.estimated_minutes} min
                          </small>
                        </span>
                      </NavLink>
                    </li>
                  )}
                  {matches.length === 0 && !reviewMatches && (
                    <li className="trail-empty">Nenhum item encontrado nesta unidade.</li>
                  )}
                </ul>
              )}
            </section>
          )
        })}
      </div>
      {curriculum && semResultado && (
        <p className="trail-empty trail-empty-course">
          Nenhuma aula ou checkpoint encontrado neste curso.
        </p>
      )}
    </div>
  )
}
