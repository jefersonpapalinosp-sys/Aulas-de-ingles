import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useSessao } from '../api/auth'
import type { CourseCurriculum, CourseSummary, LessonSummary, Progress } from '../api/client'
import { useCourseCurriculum, useCourses } from '../api/queries'
import { useMarcarEstudada, useProgress } from '../api/progress'
import {
  curriculumLessons,
  lessonProgressKey,
  matchesLessonSearch,
} from '../features/curriculum/curriculum'
import {
  coursePath,
  courseReviewPath,
  courseSlugFromPath,
  DEFAULT_COURSE_SLUG,
  lessonPath,
  unitPath,
} from '../routing/courseRoutes'

const MAX_VISIBLE_LESSONS = 12

type NavigationPanelProps = {
  idPrefix: string
  courses: CourseSummary[]
  curriculum?: CourseCurriculum
  courseSlug: string
  activeUnitSlug?: string
  activeLessonNumber?: number
  progress?: Progress
  query: string
  expandedUnit: string | null
  onQueryChange: (query: string) => void
  onCourseChange: (courseSlug: string) => void
  onUnitToggle: (unitSlug: string) => void
  onLessonDone: (lesson: LessonSummary, studied: boolean) => void
  completionPending: boolean
  searchInputRef?: React.RefObject<HTMLInputElement | null>
  activeLessonRef?: React.RefObject<HTMLAnchorElement | null>
  onNavigate?: () => void
}

function progressKeys(progress: Progress | undefined): Set<string> {
  return new Set(
    progress?.lessons
      .filter((lesson) => lesson.studied)
      .map((lesson) => lessonProgressKey(lesson.course_slug, lesson.lesson_number)) ?? [],
  )
}

function visibleWindow(lessons: LessonSummary[], activeLessonNumber?: number): LessonSummary[] {
  if (lessons.length <= MAX_VISIBLE_LESSONS) return lessons
  const activeIndex = lessons.findIndex((lesson) => lesson.number === activeLessonNumber)
  if (activeIndex < 0) return lessons.slice(0, MAX_VISIBLE_LESSONS)
  const start = Math.max(
    0,
    Math.min(
      activeIndex - Math.floor(MAX_VISIBLE_LESSONS / 2),
      lessons.length - MAX_VISIBLE_LESSONS,
    ),
  )
  return lessons.slice(start, start + MAX_VISIBLE_LESSONS)
}

export function NavigationPanel({
  idPrefix,
  courses,
  curriculum,
  courseSlug,
  activeUnitSlug,
  activeLessonNumber,
  progress,
  query,
  expandedUnit,
  onQueryChange,
  onCourseChange,
  onUnitToggle,
  onLessonDone,
  completionPending,
  searchInputRef,
  activeLessonRef,
  onNavigate,
}: NavigationPanelProps) {
  const studied = useMemo(() => progressKeys(progress), [progress])
  const courseLessons = curriculumLessons(curriculum)
  const studiedInCourse = courseLessons.filter((lesson) =>
    studied.has(lessonProgressKey(courseSlug, lesson.number)),
  ).length
  const expanded = curriculum?.units.find((unit) => unit.slug === expandedUnit)
  const studiedInUnit =
    expanded?.lessons.filter((lesson) =>
      studied.has(lessonProgressKey(courseSlug, lesson.number)),
    ).length ?? 0
  const courseTitle =
    curriculum?.course.title ?? courses.find((course) => course.slug === courseSlug)?.title

  return (
    <div className="trail-panel">
      <header className="trail-head">
        <label className="trail-course-select">
          <span>Curso</span>
          <select value={courseSlug} onChange={(event) => onCourseChange(event.target.value)}>
            {courses.map((course) => (
              <option key={course.id} value={course.slug}>
                {course.title}
              </option>
            ))}
          </select>
        </label>
        <p className="brand">{curriculum?.course.provider ?? 'Cursos de inglês'}</p>
        <h2>{courseTitle ?? 'Carregando curso…'}</h2>
        <div className="trail-progress-grid">
          <div className="prog">
            <div className="prog-top">
              <span>Aulas do curso</span>
              <span>
                {studiedInCourse}/{courseLessons.length}
              </span>
            </div>
            <div
              className="prog-bar"
              role="progressbar"
              aria-label="Progresso das aulas do curso"
              aria-valuemin={0}
              aria-valuemax={courseLessons.length}
              aria-valuenow={studiedInCourse}
            >
              <span
                className="prog-fill"
                style={{
                  width: courseLessons.length
                    ? `${(studiedInCourse / courseLessons.length) * 100}%`
                    : '0%',
                }}
              />
            </div>
          </div>
          <div className="prog">
            <div className="prog-top">
              <span>Aulas da unidade</span>
              <span>
                {studiedInUnit}/{expanded?.lessons.length ?? 0}
              </span>
            </div>
            <div
              className="prog-bar"
              role="progressbar"
              aria-label="Progresso das aulas da unidade"
              aria-valuemin={0}
              aria-valuemax={expanded?.lessons.length ?? 0}
              aria-valuenow={studiedInUnit}
            >
              <span
                className="prog-fill"
                style={{
                  width: expanded?.lessons.length
                    ? `${(studiedInUnit / expanded.lessons.length) * 100}%`
                    : '0%',
                }}
              />
            </div>
          </div>
        </div>
      </header>

      <nav className="trail-utilities" aria-label="Atalhos">
        <NavLink to="/inicio" onClick={onNavigate}>
          Hoje
        </NavLink>
        <NavLink to="/cursos" onClick={onNavigate}>
          Cursos
        </NavLink>
        <NavLink to="/revisar" onClick={onNavigate}>
          Revisar
          {Boolean(progress?.review_due) && (
            <span className="badge">{progress?.review_due}</span>
          )}
        </NavLink>
        <NavLink to="/caderno" onClick={onNavigate}>
          Caderno
        </NavLink>
        <NavLink to="/prova" onClick={onNavigate}>
          Avaliação
        </NavLink>
        {expandedUnit && (
          <NavLink to={unitPath(courseSlug, expandedUnit)} onClick={onNavigate}>
            Mapa da unidade
          </NavLink>
        )}
      </nav>

      <label className="trail-search">
        <span>Buscar aula ou checkpoint</span>
        <input
          ref={searchInputRef}
          type="search"
          value={query}
          placeholder="Número, título, tópico ou checkpoint"
          onChange={(event) => onQueryChange(event.target.value)}
        />
      </label>

      <div className="trail-scroll">
        <div className="trail-units">
          {curriculum?.units.map((unit) => {
            const matches = unit.lessons.filter((lesson) => matchesLessonSearch(lesson, query))
            const reviewMatches = Boolean(
              unit.review &&
                (!query.trim() ||
                  unit.review.title.toLocaleLowerCase('pt-BR').includes(
                    query.trim().toLocaleLowerCase('pt-BR'),
                  )),
            )
            const isExpanded = expandedUnit === unit.slug
            const visible = visibleWindow(matches, activeLessonNumber)
            return (
              <section className="trail-unit" key={unit.id}>
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
                      {unit.published_lessons}{' '}
                      {unit.published_lessons === 1 ? 'aula' : 'aulas'}
                    </small>
                  </span>
                  {unit.slug === activeUnitSlug && <em>Atual</em>}
                </button>
                {isExpanded && (
                  <ul
                    id={`${idPrefix}-trail-unit-${unit.id}`}
                    className="trail-lessons"
                    aria-label={`Itens de ${unit.title}`}
                  >
                    {visible.map((lesson) => {
                      const isActive = lesson.number === activeLessonNumber
                      const isStudied = studied.has(
                        lessonProgressKey(courseSlug, lesson.number),
                      )
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
                            aria-label={`${isStudied ? 'Desmarcar' : 'Marcar'} aula ${lesson.number} como estudada`}
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
                        <NavLink
                          to={courseReviewPath(courseSlug, unit.slug)}
                          onClick={onNavigate}
                        >
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
        {curriculum &&
          curriculum.units.every((unit) =>
            unit.lessons.every((lesson) => !matchesLessonSearch(lesson, query)) &&
            !unit.review?.title
              .toLocaleLowerCase('pt-BR')
              .includes(query.trim().toLocaleLowerCase('pt-BR')),
          ) && (
            <p className="trail-empty trail-empty-course">
              Nenhuma aula ou checkpoint encontrado neste curso.
            </p>
          )}
      </div>

    </div>
  )
}

function focusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(
    container.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((element) => !element.hasAttribute('hidden'))
}

function activeContext(pathname: string): { unitSlug?: string; lessonNumber?: number } {
  const unit = pathname.match(/\/unidades\/([^/]+)/)?.[1]
  const lesson = pathname.match(/\/aulas\/(\d+)/)?.[1]
  return {
    unitSlug: unit ? decodeURIComponent(unit) : undefined,
    lessonNumber: lesson ? Number(lesson) : undefined,
  }
}

export function LessonRail() {
  const { usuario, sair } = useSessao()
  const location = useLocation()
  const navigate = useNavigate()
  const courses = useCourses()
  const courseSlug = courseSlugFromPath(location.pathname) ?? DEFAULT_COURSE_SLUG
  const curriculum = useCourseCurriculum(courseSlug)
  const progress = useProgress(courseSlug)
  const markStudied = useMarcarEstudada(courseSlug)
  const context = activeContext(location.pathname)
  const activeLesson = curriculum.data
    ? curriculumLessons(curriculum.data).find(
        (lesson) => lesson.number === context.lessonNumber,
      )
    : undefined
  const contextualUnit = context.unitSlug ?? activeLesson?.unit_slug
  const [expandedUnit, setExpandedUnit] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const drawerRef = useRef<HTMLDivElement>(null)
  const openButtonRef = useRef<HTMLButtonElement>(null)
  const drawerSearchRef = useRef<HTMLInputElement>(null)
  const desktopActiveRef = useRef<HTMLAnchorElement>(null)
  const drawerActiveRef = useRef<HTMLAnchorElement>(null)

  useEffect(() => {
    if (!curriculum.data) return
    const fallback = curriculum.data.units[0]?.slug ?? null
    setExpandedUnit(contextualUnit ?? fallback)
  }, [courseSlug, contextualUnit, curriculum.data])

  useEffect(() => {
    if (!query.trim() || !curriculum.data) return
    const normalizedQuery = query.trim().toLocaleLowerCase('pt-BR')
    const firstMatchingUnit = curriculum.data.units.find(
      (unit) =>
        unit.lessons.some((lesson) => matchesLessonSearch(lesson, query)) ||
        unit.review?.title.toLocaleLowerCase('pt-BR').includes(normalizedQuery),
    )
    if (firstMatchingUnit) setExpandedUnit(firstMatchingUnit.slug)
  }, [query, curriculum.data])

  useEffect(() => {
    desktopActiveRef.current?.scrollIntoView?.({ block: 'nearest' })
  }, [location.pathname, expandedUnit])

  useEffect(() => {
    if (!drawerOpen) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    requestAnimationFrame(() => drawerSearchRef.current?.focus())
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [drawerOpen])

  function closeDrawer(returnFocus = true) {
    setDrawerOpen(false)
    if (returnFocus) requestAnimationFrame(() => openButtonRef.current?.focus())
  }

  function handleDrawerKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') {
      event.preventDefault()
      closeDrawer()
      return
    }
    if (event.key !== 'Tab' || !drawerRef.current) return
    const focusable = focusableElements(drawerRef.current)
    if (focusable.length === 0) return
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (!first || !last) return
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  const panelProps: Omit<
    NavigationPanelProps,
    'idPrefix' | 'searchInputRef' | 'activeLessonRef' | 'onNavigate'
  > = {
    courses: courses.data ?? [],
    curriculum: curriculum.data,
    courseSlug,
    activeUnitSlug: contextualUnit,
    activeLessonNumber: context.lessonNumber,
    progress: progress.data,
    query,
    expandedUnit,
    onQueryChange: setQuery,
    onCourseChange: (slug) => {
      setQuery('')
      void navigate(coursePath(slug))
    },
    onUnitToggle: (slug) =>
      setExpandedUnit((current) => (current === slug ? null : slug)),
    onLessonDone: (lesson, studied) =>
      markStudied.mutate({ numero: lesson.number, estudada: studied }),
    completionPending: markStudied.isPending,
  }

  const contextualUnitData = curriculum.data?.units.find(
    (unit) => unit.slug === contextualUnit,
  )
  const activeCheckpoint = /\/checkpoint\/?$/.test(location.pathname)
    ? contextualUnitData?.review
    : undefined
  const mobileLabel = activeLesson
    ? `Aula ${activeLesson.number} · ${activeLesson.title}`
    : activeCheckpoint?.title ??
      contextualUnitData?.title ??
      curriculum.data?.course.title ??
      'Escolher aula'

  return (
    <aside className="navigation-shell" aria-label="Navegação do curso">
      <div className="rail">
        <NavigationPanel
          {...panelProps}
          idPrefix="desktop"
          activeLessonRef={desktopActiveRef}
        />
        {usuario && (
          <p className="trail-account">
            <span>{usuario.display_name}</span>
            <button type="button" onClick={() => void sair()}>
              Sair
            </button>
          </p>
        )}
      </div>

      <div className="mobile-trail-bar">
        <button
          ref={openButtonRef}
          type="button"
          aria-haspopup="dialog"
          aria-expanded={drawerOpen}
          onClick={() => setDrawerOpen(true)}
        >
          <span>
            <small>Trilha atual</small>
            <strong>{mobileLabel}</strong>
          </span>
          <span aria-hidden="true">☰</span>
          <span className="sr-only">Abrir trilha de aulas</span>
        </button>
      </div>

      {drawerOpen && (
        <div
          className="trail-drawer-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeDrawer()
          }}
        >
          <div
            ref={drawerRef}
            className="trail-drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="trail-drawer-title"
            onKeyDown={handleDrawerKeyDown}
          >
            <div className="trail-drawer-titlebar">
              <h2 id="trail-drawer-title">Trilha de estudo</h2>
              <button type="button" onClick={() => closeDrawer()} aria-label="Fechar trilha">
                ×
              </button>
            </div>
            <NavigationPanel
              {...panelProps}
              idPrefix="drawer"
              searchInputRef={drawerSearchRef}
              activeLessonRef={drawerActiveRef}
              onNavigate={() => closeDrawer(false)}
            />
          </div>
        </div>
      )}
    </aside>
  )
}
