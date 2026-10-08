import { Link } from 'react-router-dom'
import { studyPath } from '../../routing/courseRoutes'
import { STUDY_STEPS, type StudyStepSlug } from './studyProgress'

export function StepNavigator({
  courseSlug,
  lessonNumber,
  currentStep,
  completedSteps,
}: {
  courseSlug: string
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
                to={studyPath(courseSlug, lessonNumber, step.slug)}
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
