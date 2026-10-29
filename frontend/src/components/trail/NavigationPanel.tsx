import { useMemo } from 'react'
import type { CourseCurriculum, CourseSummary, LessonSummary, Progress } from '../../api/client'
import { curriculumLessons, lessonProgressKey } from '../../features/curriculum/curriculum'
import { courseLevelLabel } from '../../routing/courseRoutes'
import { TrailHeader } from './TrailHeader'
import { TrailShortcuts } from './TrailShortcuts'
import { TrailUnits } from './TrailUnits'

export type NavigationPanelProps = {
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
  const courseLevel = courseLevelLabel(courseSlug)
  const requestedScopeUnit = activeUnitSlug ?? expandedUnit ?? undefined
  const scopedUnit = curriculum?.units.find((unit) => unit.slug === requestedScopeUnit)
  const scopeUnitSlug =
    scopedUnit?.status === 'published' && scopedUnit.published_lessons > 0
      ? scopedUnit.slug
      : undefined

  return (
    <div className="trail-panel">
      <TrailHeader
        courses={courses}
        courseSlug={courseSlug}
        courseTitle={courseTitle}
        provider={curriculum?.course.provider}
        onCourseChange={onCourseChange}
        studiedInCourse={studiedInCourse}
        lessonsInCourse={courseLessons.length}
        studiedInUnit={studiedInUnit}
        lessonsInUnit={expanded?.lessons.length ?? 0}
      />

      <TrailShortcuts
        courseSlug={courseSlug}
        scopeUnitSlug={scopeUnitSlug}
        reviewDue={progress?.review_due}
        onNavigate={onNavigate}
      />

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

      <TrailUnits
        idPrefix={idPrefix}
        curriculum={curriculum}
        courseSlug={courseSlug}
        courseLevel={courseLevel}
        query={query}
        expandedUnit={expandedUnit}
        activeUnitSlug={activeUnitSlug}
        activeLessonNumber={activeLessonNumber}
        studied={studied}
        completionPending={completionPending}
        activeLessonRef={activeLessonRef}
        onUnitToggle={onUnitToggle}
        onLessonDone={onLessonDone}
        onNavigate={onNavigate}
      />
    </div>
  )
}
