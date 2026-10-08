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

export function studyProgressKey(userId: number, lessonNumber: number): string {
  return `aulas-ingles:study-progress:v1:${userId}:${lessonNumber}`
}

export function loadStudyProgress(userId: number, lessonNumber: number): StudyProgress {
  const initial: StudyProgress = { currentStep: FIRST_STEP, completedSteps: [] }
  if (typeof window === 'undefined') return initial

  try {
    const raw = window.localStorage.getItem(studyProgressKey(userId, lessonNumber))
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
): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(studyProgressKey(userId, lessonNumber), JSON.stringify(progress))
}
