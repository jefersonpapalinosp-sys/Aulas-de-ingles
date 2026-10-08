import { Link } from 'react-router-dom'
import { STUDY_STEPS, type StudyStepSlug } from './studyProgress'

export function StepNavigator({
  lessonNumber,
  currentStep,
  completedSteps,
}: {
  lessonNumber: number
  currentStep: StudyStepSlug
  completedSteps: StudyStepSlug[]
}) {
  const completed = new Set(completedSteps)

  return (
    <nav className="study-steps" aria-label="Etapas desta aula">
      <ol>
        {STUDY_STEPS.map((step, index) => {
          const active = step.slug === currentStep
          const done = completed.has(step.slug)
          return (
            <li key={step.slug} className={active ? 'active' : done ? 'complete' : ''}>
              <Link
                to={`/aulas/${lessonNumber}/estudar/${step.slug}`}
                aria-current={active ? 'step' : undefined}
                aria-label={`${index + 1}. ${step.title}${done ? ', concluída' : ''}`}
              >
                <span className="study-step-number" aria-hidden="true">
                  {done ? '✓' : index + 1}
                </span>
                <span>{step.shortTitle}</span>
              </Link>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
