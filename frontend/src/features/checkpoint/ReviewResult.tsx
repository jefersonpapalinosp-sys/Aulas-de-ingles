import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import type { CourseReviewAttempt } from '../../api/client'
import {
  courseLevelLabel,
  coursePath,
  DEFAULT_COURSE_SLUG,
  lessonPath,
} from '../../routing/courseRoutes'

/** Referência curta da aula.
 *
 * O nível só entra quando o curso não é o padrão: em um curso só, repetir o
 * nível em cada linha vira ruído.
 */
export function lessonReference(courseSlug: string, lessonNumber: number): string {
  return courseSlug === DEFAULT_COURSE_SLUG
    ? `Aula ${lessonNumber}`
    : `${courseLevelLabel(courseSlug)} · Aula ${lessonNumber}`
}

export function ReviewResult({
  result,
  courseSlug,
  nextLessonNumber,
  completionHref,
  onRetry,
}: {
  result: CourseReviewAttempt
  courseSlug: string
  nextLessonNumber?: number
  completionHref?: string
  onRetry: () => void
}) {
  const consolidated = result.status === 'consolidated'
  const titleRef = useRef<HTMLHeadingElement>(null)
  const titleId = `checkpoint-result-title-${result.id}`

  useEffect(() => {
    titleRef.current?.focus()
  }, [result.id])

  return (
    <section
      className={`checkpoint-result ${consolidated ? 'is-success' : 'needs-review'}`}
      role="status"
      aria-live="polite"
      aria-labelledby={titleId}
    >
      <p className="study-kicker">Resultado salvo</p>
      <div className="checkpoint-result-head">
        <div>
          <h2 id={titleId} ref={titleRef} tabIndex={-1}>
            {consolidated ? 'Bloco consolidado' : 'Vale reforçar alguns pontos'}
          </h2>
          <p>
            Você acertou {result.score} de {result.total} questões ({result.score_percent}%).
          </p>
        </div>
        <strong aria-label={`${result.score_percent} por cento`}>{result.score_percent}%</strong>
      </div>

      {result.reinforced_lesson_numbers.length > 0 && (
        <div className="checkpoint-reinforce">
          <h3>Retomar antes da próxima tentativa</h3>
          <div>
            {result.reinforced_lesson_numbers.map((number) => (
              <Link key={number} to={lessonPath(courseSlug, number)}>
                {lessonReference(courseSlug, number)}
              </Link>
            ))}
          </div>
        </div>
      )}

      <ol className="checkpoint-feedback">
        {result.feedback.map((item) => (
          <li key={item.question_id} className={item.correct ? 'correct' : 'incorrect'}>
            <strong>{item.correct ? 'Correta' : 'Revisar'}</strong>
            <p>{item.explanation}</p>
            {!item.correct && (
              <small>
                Sua resposta: {item.answer} · resposta esperada: {item.accepted_answers.join(' / ')}
              </small>
            )}
          </li>
        ))}
      </ol>

      <div className="checkpoint-actions">
        <button type="button" className="btn" onClick={onRetry}>
          Refazer checkpoint
        </button>
        {nextLessonNumber !== undefined && (
          <Link className="btn" to={lessonPath(courseSlug, nextLessonNumber)}>
            {courseSlug === DEFAULT_COURSE_SLUG
              ? `Continuar na Aula ${nextLessonNumber}`
              : `Continuar em ${lessonReference(courseSlug, nextLessonNumber)}`}
          </Link>
        )}
        {completionHref && (
          <Link className="btn" to={completionHref}>
            Ver progresso do curso
          </Link>
        )}
        <Link className="btn ghost" to={coursePath(courseSlug)}>
          Voltar ao mapa
        </Link>
      </div>
    </section>
  )
}
