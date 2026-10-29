import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useSessao } from '../api/auth'
import type { CourseCurriculum } from '../api/client'
import { useCourseCurriculum, useCourses } from '../api/queries'
import { useMarcarEstudada, useProgress } from '../api/progress'
import { curriculumLessons, matchesLessonSearch } from '../features/curriculum/curriculum'

import { NavigationPanel, type NavigationPanelProps } from './trail/NavigationPanel'
import { TrailDrawer } from './trail/TrailDrawer'
import { trailLabel } from './trail/trailLabel'
import { useTrailDrawer } from './trail/useTrailDrawer'
import {
  courseLevelLabel,
  coursePath,
  courseSlugFromPath,
  DEFAULT_COURSE_SLUG,
  notebookPath,
  reviewPath,
  todayPath,
} from '../routing/courseRoutes'

function firstUnitMatching(
  curriculum: CourseCurriculum | undefined,
  query: string,
): string | null {
  const normalized = query.trim().toLocaleLowerCase('pt-BR')
  if (!normalized || !curriculum) return null
  return (
    curriculum.units.find(
      (unit) =>
        unit.lessons.some((lesson) => matchesLessonSearch(lesson, query)) ||
        unit.review?.title.toLocaleLowerCase('pt-BR').includes(normalized),
    )?.slug ?? null
  )
}

function activeContext(pathname: string): { unitSlug?: string; lessonNumber?: number } {
  const unit = pathname.match(/\/unidades\/([^/]+)/)?.[1]
  const lesson = pathname.match(/\/aulas\/(\d+)/)?.[1]
  return {
    unitSlug: unit ? decodeURIComponent(unit) : undefined,
    lessonNumber: lesson ? Number(lesson) : undefined,
  }
}

function courseSwitchPath(pathname: string, courseSlug: string): string {
  if (pathname === '/' || pathname === '/inicio') return todayPath(courseSlug)
  if (pathname === '/revisar') return reviewPath(courseSlug)
  if (pathname === '/caderno') return notebookPath(courseSlug)
  return coursePath(courseSlug)
}

export function LessonRail() {
  const { usuario, sair } = useSessao()
  const location = useLocation()
  const navigate = useNavigate()
  const courses = useCourses()
  const search = new URLSearchParams(location.search)
  const courseSlug =
    courseSlugFromPath(location.pathname) ??
    search.get('course') ??
    DEFAULT_COURSE_SLUG
  const curriculum = useCourseCurriculum(courseSlug)
  const progress = useProgress(courseSlug)
  const markStudied = useMarcarEstudada(courseSlug)
  const context = activeContext(location.pathname)
  const activeLesson = curriculum.data
    ? curriculumLessons(curriculum.data).find(
        (lesson) => lesson.number === context.lessonNumber,
      )
    : undefined
  const contextualUnit =
    context.unitSlug ?? search.get('unit') ?? activeLesson?.unit_slug
  // A unidade aberta é derivada do contexto da rota, mas uma escolha do aluno
  // vence até ele mudar de curso ou de unidade. Guardar a escolha junto do
  // escopo é o que faz o toggle sobreviver a um refetch do currículo: antes
  // isso era um useEffect que dependia de `curriculum.data` e, a cada
  // revalidação, fechava a unidade que o aluno tinha aberto.
  const [unitChoice, setUnitChoice] = useState<{ scope: string; unit: string | null } | null>(null)
  const [query, setQuery] = useState('')
  const drawer = useTrailDrawer()
  const desktopActiveRef = useRef<HTMLAnchorElement>(null)
  const drawerActiveRef = useRef<HTMLAnchorElement>(null)

  const unitScope = `${courseSlug}:${contextualUnit ?? ''}`
  const searchedUnit = useMemo(
    () => firstUnitMatching(curriculum.data, query),
    [curriculum.data, query],
  )
  // Precedência: escolha do aluno neste escopo > primeira unidade que casa com
  // a busca > unidade do contexto da rota > primeira do currículo. Nenhum
  // efeito escreve aqui, então revalidar o currículo não muda o que está
  // aberto; digitar na busca limpa a escolha e devolve a precedência à busca.
  const expandedUnit =
    unitChoice?.scope === unitScope
      ? unitChoice.unit
      : (searchedUnit ?? contextualUnit ?? curriculum.data?.units[0]?.slug ?? null)

  useEffect(() => {
    desktopActiveRef.current?.scrollIntoView?.({ block: 'nearest' })
  }, [location.pathname, expandedUnit])

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
    onQueryChange: (next) => {
      setQuery(next)
      setUnitChoice(null)
    },
    onCourseChange: (slug) => {
      setQuery('')
      void navigate(courseSwitchPath(location.pathname, slug))
    },
    onUnitToggle: (slug) =>
      setUnitChoice({ scope: unitScope, unit: expandedUnit === slug ? null : slug }),
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
  const mobileLabel = trailLabel({
    levelLabel: courseLevelLabel(courseSlug),
    lesson: activeLesson,
    checkpoint: activeCheckpoint,
    unit: contextualUnitData,
    courseTitle: curriculum.data?.course.title,
  })

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

      <TrailDrawer
        label={mobileLabel}
        open={drawer.open}
        drawerRef={drawer.drawerRef}
        openButtonRef={drawer.openButtonRef}
        onOpen={drawer.openDrawer}
        onClose={drawer.close}
        onKeyDown={drawer.onKeyDown}
      >
        <NavigationPanel
          {...panelProps}
          idPrefix="drawer"
          searchInputRef={drawer.searchRef}
          activeLessonRef={drawerActiveRef}
          onNavigate={() => drawer.close(false)}
        />
      </TrailDrawer>
    </aside>
  )
}
