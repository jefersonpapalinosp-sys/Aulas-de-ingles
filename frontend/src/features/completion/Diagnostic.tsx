import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import type { CourseCompletion } from '../../api/client'
import { coursePath } from '../../routing/courseRoutes'
import { levelLabel } from './completionLabels'

type DiagnosticChoice = 'yes' | 'partial' | 'not_yet'
type DiagnosticQuestionId = 'listening' | 'language' | 'review'

const diagnosticQuestions: ReadonlyArray<{
  id: DiagnosticQuestionId
  prompt: string
}> = [
  {
    id: 'listening',
    prompt: 'Consigo acompanhar a ideia principal de um diálogo curto sem ler tudo?',
  },
  {
    id: 'language',
    prompt: 'Consigo falar ou escrever sobre experiências usando estruturas já estudadas?',
  },
  {
    id: 'review',
    prompt: 'Consigo perceber quando preciso revisar vocabulário, gramática ou listening?',
  },
]

const diagnosticChoices: ReadonlyArray<{
  value: DiagnosticChoice
  label: string
}> = [
  { value: 'yes', label: 'Sim' },
  { value: 'partial', label: 'Em parte' },
  { value: 'not_yet', label: 'Ainda não' },
]

export function Diagnostic({ data }: { data: CourseCompletion }) {
  const nextCourse = data.next_course
  const [answers, setAnswers] = useState<Partial<Record<DiagnosticQuestionId, DiagnosticChoice>>>(
    {},
  )
  const [showGuidance, setShowGuidance] = useState(false)
  const guidanceHeading = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    if (showGuidance) guidanceHeading.current?.focus()
  }, [showGuidance])

  if (!nextCourse) return null

  const nextLevel = nextCourse.level
  const nextLevelLabel = levelLabel(nextLevel)
  const currentLevelLabel = levelLabel(data.course.level)
  const complete = diagnosticQuestions.every((question) => answers[question.id])
  const values = diagnosticQuestions.map((question) => answers[question.id])
  const hasNotYet = values.includes('not_yet')
  const allYes = values.every((value) => value === 'yes')

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (complete) setShowGuidance(true)
  }

  function guidance() {
    if (allYes) {
      return {
        title: `Você pode explorar ${nextLevelLabel} agora`,
        copy: `Mantenha revisões curtas do ${currentLevelLabel} enquanto conhece o próximo nível.`,
      }
    }
    if (hasNotYet) {
      return {
        title: 'Revise no seu ritmo antes ou em paralelo',
        copy: `Retome os pontos sinalizados e explore ${nextLevelLabel} quando quiser. O próximo nível continua opcional.`,
      }
    }
    return {
      title: `Explore ${nextLevelLabel} mantendo revisões`,
      copy: 'Você pode conhecer o próximo nível e reforçar os pontos em que respondeu “Em parte”.',
    }
  }

  const result = guidance()

  return (
    <section
      className="completion-diagnostic"
      id="diagnostico"
      aria-labelledby="diagnostic-title"
      tabIndex={-1}
    >
      <p className="eyebrow">Autoavaliação curta · antes do próximo nível</p>
      <h2 id="diagnostic-title">{nextCourse.diagnostic.title}</h2>
      <p>{nextCourse.diagnostic.description}</p>
      <p className="completion-diagnostic-disclaimer">
        Esta autoavaliação não é prova, não gera nota e não altera seu progresso.
      </p>

      <form onSubmit={submit}>
        {diagnosticQuestions.map((question, questionIndex) => (
          <fieldset key={question.id}>
            <legend>
              <span>{questionIndex + 1}</span>
              {question.prompt}
            </legend>
            <div className="completion-diagnostic-options">
              {diagnosticChoices.map((choice) => (
                <label key={choice.value}>
                  <input
                    type="radio"
                    name={`diagnostic-${question.id}`}
                    value={choice.value}
                    checked={answers[question.id] === choice.value}
                    onChange={() => {
                      setAnswers((current) => ({ ...current, [question.id]: choice.value }))
                      setShowGuidance(false)
                    }}
                  />
                  <span>{choice.label}</span>
                </label>
              ))}
            </div>
          </fieldset>
        ))}
        <button className="btn" type="submit" disabled={!complete}>
          Ver orientação
        </button>
      </form>

      {showGuidance && (
        <div className="completion-diagnostic-result" role="status" aria-live="polite">
          <h3 ref={guidanceHeading} tabIndex={-1}>
            {result.title}
          </h3>
          <p>{result.copy}</p>
          <div className="completion-actions">
            <Link className="btn" to={nextCourse.href}>
              Conhecer {nextLevelLabel}
            </Link>
            <Link
              className="btn ghost"
              to={data.incomplete_units[0]?.href ?? coursePath(data.course.slug)}
            >
              Revisar {currentLevelLabel}
            </Link>
          </div>
        </div>
      )}
    </section>
  )
}
