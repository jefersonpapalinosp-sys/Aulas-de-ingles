export const STUDY_STEPS = [
  { slug: 'preparar', title: 'Preparar', shortTitle: 'Preparar' },
  { slug: 'assistir', title: 'Assistir e ouvir', shortTitle: 'Assistir' },
  { slug: 'estudar', title: 'Estudar a teoria', shortTitle: 'Estudar' },
  { slug: 'praticar', title: 'Praticar', shortTitle: 'Praticar' },
  { slug: 'revisar', title: 'Revisar', shortTitle: 'Revisar' },
] as const

export type StudyStepSlug = (typeof STUDY_STEPS)[number]['slug']

export type StudyProgress = {
  currentStep: StudyStepSlug
  completedSteps: StudyStepSlug[]
}
const FIRST_STEP = STUDY_STEPS[0].slug

export function isStudyStep(value: string | undefined): value is StudyStepSlug {
  return STUDY_STEPS.some((step) => step.slug === value)
}

function progressIdentity(
  courseSlugOrLessonNumber: string | number,
  lessonNumber?: number,
): { courseSlug: string; lessonNumber: number } {
  return typeof courseSlugOrLessonNumber === 'string'
    ? { courseSlug: courseSlugOrLessonNumber, lessonNumber: lessonNumber ?? Number.NaN }
    : { courseSlug: 'voa-level-1', lessonNumber: courseSlugOrLessonNumber }
}

export function studyProgressKey(
  userId: number,
  courseSlugOrLessonNumber: string | number,
  lessonNumber?: number,
): string {
  const identity = progressIdentity(courseSlugOrLessonNumber, lessonNumber)
  return `aulas-ingles:study-progress:v2:${userId}:${identity.courseSlug}:${identity.lessonNumber}`
}

export function loadStudyProgress(userId: number, lessonNumber: number): StudyProgress
export function loadStudyProgress(
  userId: number,
  courseSlug: string,
  lessonNumber: number,
): StudyProgress
export function loadStudyProgress(
  userId: number,
  courseSlugOrLessonNumber: string | number,
  maybeLessonNumber?: number,
): StudyProgress {
  const initial: StudyProgress = { currentStep: FIRST_STEP, completedSteps: [] }
  if (typeof window === 'undefined') return initial

  try {
    const { courseSlug, lessonNumber } = progressIdentity(
      courseSlugOrLessonNumber,
      maybeLessonNumber,
    )
    const key = studyProgressKey(userId, courseSlug, lessonNumber)
    let raw = window.localStorage.getItem(key)
    // Migração transparente dos dados locais anteriores à identidade multi-curso.
    if (!raw && courseSlug === 'voa-level-1') {
      raw = window.localStorage.getItem(`aulas-ingles:study-progress:v1:${userId}:${lessonNumber}`)
      if (raw) window.localStorage.setItem(key, raw)
    }
    if (!raw) return initial

    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return initial

    const candidate = parsed as { currentStep?: unknown; completedSteps?: unknown }
    const currentStep =
      typeof candidate.currentStep === 'string' && isStudyStep(candidate.currentStep)
        ? candidate.currentStep
        : FIRST_STEP
    const completedSteps = Array.isArray(candidate.completedSteps)
      ? candidate.completedSteps.filter(
          (step): step is StudyStepSlug => typeof step === 'string' && isStudyStep(step),
        )
      : []

    return { currentStep, completedSteps: [...new Set(completedSteps)] }
  } catch {
    return initial
  }
}

export function saveStudyProgress(
  userId: number,
  lessonNumber: number,
  progress: StudyProgress,
): void
export function saveStudyProgress(
  userId: number,
  courseSlug: string,
  lessonNumber: number,
  progress: StudyProgress,
): void
export function saveStudyProgress(
  userId: number,
  courseSlugOrLessonNumber: string | number,
  lessonNumberOrProgress: number | StudyProgress,
  maybeProgress?: StudyProgress,
): void {
  if (typeof window === 'undefined') return
  const legacyCall = typeof courseSlugOrLessonNumber === 'number'
  const courseSlug = legacyCall ? 'voa-level-1' : courseSlugOrLessonNumber
  const lessonNumber = legacyCall
    ? courseSlugOrLessonNumber
    : (lessonNumberOrProgress as number)
  const progress = legacyCall ? (lessonNumberOrProgress as StudyProgress) : maybeProgress
  if (!progress) return
  window.localStorage.setItem(
    studyProgressKey(userId, courseSlug, lessonNumber),
    JSON.stringify(progress),
  )
}
