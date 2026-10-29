// Retirada do adaptador legado: alvo 2027-01-29, condicionada à preservação/recuperação.
// Critérios: docs/politica_migracoes_storage_2026-10-29.md. Não expira nem apaga dados.
import { readLocal, writeLocal } from '../../storage/local'

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
  return readStudyProgress(userId, courseSlugOrLessonNumber, maybeLessonNumber).progress
}

export function readStudyProgress(userId: number, courseSlugOrLessonNumber: string | number,
  maybeLessonNumber?: number): { progress: StudyProgress; warning: string } {
  const initial: StudyProgress = { currentStep: FIRST_STEP, completedSteps: [] }
  let warning = ''

  try {
    const { courseSlug, lessonNumber } = progressIdentity(
      courseSlugOrLessonNumber,
      maybeLessonNumber,
    )
    const key = studyProgressKey(userId, courseSlug, lessonNumber)
    const local = readLocal(key)
    if (!local.ok) return { progress: initial, warning: local.error }
    let raw = local.value
    // Migração transparente dos dados locais anteriores à identidade multi-curso.
    if (!raw && courseSlug === 'voa-level-1') {
      const legacy = readLocal(`aulas-ingles:study-progress:v1:${userId}:${lessonNumber}`)
      if (!legacy.ok) return { progress: initial, warning: legacy.error }
      raw = legacy.value
      if (raw) {
        const migrated = writeLocal(key, raw)
        if (!migrated.ok) warning = migrated.error
      }
    }
    if (!raw) return { progress: initial, warning }

    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') throw new Error('Invalid progress')

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

    return { progress: { currentStep, completedSteps: [...new Set(completedSteps)] }, warning }
  } catch {
    return { progress: initial, warning: 'Jornada local indisponível. Confira o progresso da conta.' }
  }
}

export function saveStudyProgress(
  userId: number,
  lessonNumber: number,
  progress: StudyProgress,
): boolean
export function saveStudyProgress(
  userId: number,
  courseSlug: string,
  lessonNumber: number,
  progress: StudyProgress,
): boolean
export function saveStudyProgress(
  userId: number,
  courseSlugOrLessonNumber: string | number,
  lessonNumberOrProgress: number | StudyProgress,
  maybeProgress?: StudyProgress,
): boolean {
  const legacyCall = typeof courseSlugOrLessonNumber === 'number'
  const courseSlug = legacyCall ? 'voa-level-1' : courseSlugOrLessonNumber
  const lessonNumber = legacyCall
    ? courseSlugOrLessonNumber
    : (lessonNumberOrProgress as number)
  const progress = legacyCall ? (lessonNumberOrProgress as StudyProgress) : maybeProgress
  if (!progress) return false
  return writeLocal(
    studyProgressKey(userId, courseSlug, lessonNumber),
    JSON.stringify(progress),
  ).ok
}
