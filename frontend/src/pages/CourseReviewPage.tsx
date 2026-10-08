import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useSessao } from '../api/auth'
import type { CourseReviewAttempt } from '../api/client'
import { useCourseReview, useSubmitCourseReview } from '../api/courseReviews'
import { Carregando, Erro } from '../components/States'
import { LessonAudioPlayer } from '../features/media/LessonAudioPlayer'
import {
  coursePath,
  DEFAULT_COURSE_SLUG,
  lessonPath,
  unitPath,
} from '../routing/courseRoutes'

function ReviewResult({
  result,
  courseSlug,
  onRetry,
}: {
  result: CourseReviewAttempt
  courseSlug: string
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
                Aula {number}
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
        <Link className="btn ghost" to={coursePath(courseSlug)}>
          Voltar ao mapa
        </Link>
      </div>
    </section>
  )
}

export function CourseReviewPage() {
  const { courseSlug = DEFAULT_COURSE_SLUG, unitSlug = '' } = useParams()
  return (
    <CourseReviewContent
      key={`${courseSlug}/${unitSlug}`}
      courseSlug={courseSlug}
      unitSlug={unitSlug}
    />
  )
}

function CourseReviewContent({
  courseSlug,
  unitSlug,
}: {
  courseSlug: string
  unitSlug: string
}) {
  const { usuario } = useSessao()
  const review = useCourseReview(courseSlug, unitSlug)
  const submit = useSubmitCourseReview(courseSlug, unitSlug)
  const [answers, setAnswers] = useState<Record<number, string>>({})
  const [retrying, setRetrying] = useState(false)
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID())
  const firstAnswerRef = useRef<HTMLInputElement>(null)

  const answered = useMemo(
    () => Object.values(answers).filter((answer) => answer.trim()).length,
    [answers],
  )

  if (!usuario) return null
  if (review.isPending) return <Carregando oque="o checkpoint da unidade" />
  if (review.error) {
    return <Erro erro={review.error} aoTentarDeNovo={() => void review.refetch()} />
  }

  const data = review.data
  const result = submit.data ?? (!retrying ? data.latest_attempt : null)

  function send(event: FormEvent) {
    event.preventDefault()
    if (answered !== data.questions.length || submit.isPending) return
    submit.mutate({
      idempotency_key: idempotencyKey,
      content_version: data.content_version,
      answers: data.questions.map((question) => ({
        question_id: question.id,
        answer: answers[question.id] ?? '',
      })),
    })
  }

  function retry() {
    setAnswers({})
    setRetrying(true)
    setIdempotencyKey(crypto.randomUUID())
    submit.reset()
    window.scrollTo({ top: 0, behavior: 'smooth' })
    requestAnimationFrame(() => firstAnswerRef.current?.focus())
  }

  return (
    <article className="checkpoint-page">
      <header className="checkpoint-header">
        <div>
          <p className="eyebrow">Checkpoint curricular · unidade {unitSlug}</p>
          <h1>{data.title}</h1>
          <p className="lead">{data.intro}</p>
        </div>
        <span>{data.estimated_minutes} min</span>
      </header>

      <section className="checkpoint-provenance" aria-label="Origem do checkpoint">
        <div>
          <span>Base curricular</span>
          {data.source_url ? (
            <a href={data.source_url} target="_blank" rel="noopener noreferrer">
              {data.source_title} ↗
            </a>
          ) : (
            <strong>{data.source_title}</strong>
          )}
        </div>
        <div>
          <span>Atividades</span>
          <strong>Conteúdo autoral do projeto</strong>
        </div>
        <p>{data.source_note}</p>
      </section>

      {result ? (
        <ReviewResult result={result} courseSlug={courseSlug} onRetry={retry} />
      ) : (
        <>
          <section className="checkpoint-listening">
            <div className="checkpoint-section-head">
              <div>
                <p className="study-kicker">Retomada de listening</p>
                <h2>Volte à escuta da Aula {data.review_lesson_number}</h2>
              </div>
              <Link className="btn ghost" to={lessonPath(courseSlug, data.review_lesson_number)}>
                Rever Aula {data.review_lesson_number}
              </Link>
            </div>
            {data.listening_media ? (
              <LessonAudioPlayer
                media={data.listening_media}
                userId={usuario.id}
                sourcePageUrl={
                  data.listening_source_page_url ??
                  lessonPath(courseSlug, data.review_lesson_number)
                }
              />
            ) : (
              <div className="media-fallback" role="note">
                <strong>Áudio indisponível neste checkpoint.</strong>
                <p>
                  Use a transcrição e o áudio da Aula {data.review_lesson_number} antes de
                  responder à questão de compreensão.
                </p>
              </div>
            )}
          </section>

          <form className="checkpoint-form" onSubmit={send}>
            <div className="checkpoint-progress-row">
              <div>
                <p className="study-kicker">Seu progresso</p>
                <strong>
                  {answered}/{data.questions.length} respondidas
                </strong>
              </div>
              <div
                className="checkpoint-progress"
                role="progressbar"
                aria-label="Questões respondidas"
                aria-valuemin={0}
                aria-valuemax={data.questions.length}
                aria-valuenow={answered}
              >
                <span style={{ width: `${(answered / data.questions.length) * 100}%` }} />
              </div>
            </div>

            <ol className="checkpoint-questions">
              {data.questions.map((question, questionIndex) => (
                <li key={question.id}>
                  <fieldset>
                    <legend>
                      <span>
                        {question.position}. {question.skill === 'listening' ? 'Listening' : 'Prática'}
                      </span>
                      {question.prompt}
                    </legend>
                    {question.options ? (
                      <div className="checkpoint-options">
                        {question.options.map((option, optionIndex) => (
                          <label key={option}>
                            <input
                              ref={
                                questionIndex === 0 && optionIndex === 0
                                  ? firstAnswerRef
                                  : undefined
                              }
                              type="radio"
                              name={`question-${question.id}`}
                              value={option}
                              checked={answers[question.id] === option}
                              onChange={(event) =>
                                setAnswers((current) => ({
                                  ...current,
                                  [question.id]: event.target.value,
                                }))
                              }
                            />
                            <span>{option}</span>
                          </label>
                        ))}
                      </div>
                    ) : (
                      <>
                        <label className="sr-only" htmlFor={`checkpoint-answer-${question.id}`}>
                          Resposta para: {question.prompt}
                        </label>
                        <input
                          ref={questionIndex === 0 ? firstAnswerRef : undefined}
                          id={`checkpoint-answer-${question.id}`}
                          type="text"
                          maxLength={500}
                          value={answers[question.id] ?? ''}
                          onChange={(event) =>
                            setAnswers((current) => ({
                              ...current,
                              [question.id]: event.target.value,
                            }))
                          }
                        />
                      </>
                    )}
                  </fieldset>
                </li>
              ))}
            </ol>

            {submit.error && (
              <p className="erro" role="alert">
                {submit.error.message}
              </p>
            )}
            <div className="checkpoint-actions">
              <Link className="btn ghost" to={unitPath(courseSlug, unitSlug)}>
                Voltar à unidade
              </Link>
              <button
                type="submit"
                className="btn"
                disabled={answered !== data.questions.length || submit.isPending}
              >
                {submit.isPending ? 'Corrigindo…' : 'Concluir checkpoint'}
              </button>
            </div>
          </form>
        </>
      )}
    </article>
  )
}
