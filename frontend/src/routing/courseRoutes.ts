import type { StudyStepSlug } from '../features/study-session/studyProgress'

export const DEFAULT_COURSE_SLUG = 'voa-level-1'

export function coursePath(courseSlug: string): string {
  return `/cursos/${encodeURIComponent(courseSlug)}`
}

export function unitPath(courseSlug: string, unitSlug: string): string {
  return `${coursePath(courseSlug)}/unidades/${encodeURIComponent(unitSlug)}`
}

export function lessonPath(courseSlug: string, lessonNumber: number): string {
  return `${coursePath(courseSlug)}/aulas/${lessonNumber}`
}

export function studyPath(
  courseSlug: string,
  lessonNumber: number,
  step?: StudyStepSlug,
): string {
  const base = `${lessonPath(courseSlug, lessonNumber)}/estudar`
  return step ? `${base}/${step}` : base
}

export function courseSlugFromPath(pathname: string): string | null {
  const match = pathname.match(/^\/cursos\/([^/]+)/)
  return match?.[1] ? decodeURIComponent(match[1]) : null
}

/** Converte links antigos emitidos por versões anteriores da API para a URL canônica. */
export function canonicalizeLegacyHref(href: string): string {
  const match = href.match(/^\/aulas\/(\d+)(\/estudar(?:\/[^/?#]+)?)?([?#].*)?$/)
  if (!match) return href
  return `${lessonPath(DEFAULT_COURSE_SLUG, Number(match[1]!))}${match[2] ?? ''}${match[3] ?? ''}`
}
