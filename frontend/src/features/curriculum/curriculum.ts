import type { CourseCurriculum, LessonSummary } from '../../api/client'

export function curriculumLessons(curriculum: CourseCurriculum | undefined): LessonSummary[] {
  return (
    curriculum?.units
      .slice()
      .sort((a, b) => a.position - b.position)
      .flatMap((unit) => unit.lessons.slice().sort((a, b) => a.position - b.position)) ?? []
  )
}

export function lessonProgressKey(courseSlug: string, lessonNumber: number): string {
  return `${courseSlug}:${lessonNumber}`
}

export function adjacentLessons(
  curriculum: CourseCurriculum | undefined,
  lessonId: number,
): { previous?: LessonSummary; next?: LessonSummary } {
  const lessons = curriculumLessons(curriculum)
  const index = lessons.findIndex((lesson) => lesson.id === lessonId)
  if (index < 0) return {}
  return { previous: lessons[index - 1], next: lessons[index + 1] }
}

export function matchesLessonSearch(lesson: LessonSummary, rawQuery: string): boolean {
  const query = rawQuery.trim().toLocaleLowerCase('pt-BR')
  if (!query) return true
  return [lesson.number, lesson.title, lesson.title_pt, lesson.grammar_tag]
    .join(' ')
    .toLocaleLowerCase('pt-BR')
    .includes(query)
}
