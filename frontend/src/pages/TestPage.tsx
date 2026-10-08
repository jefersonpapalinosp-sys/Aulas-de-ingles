import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useSessao } from '../api/auth'
import { useAllExercises, useCourseCurriculum } from '../api/queries'
import { ExerciseCard } from '../components/ExerciseCard'
import { Carregando, Erro } from '../components/States'
import { coursePath, DEFAULT_COURSE_SLUG, unitPath } from '../routing/courseRoutes'

/** Uma questão por aula dentro do escopo; curso + número evitam colisões entre níveis. */
function umaPorAula<
  T extends {
    course_slug: string
    lesson_number: number
    position: number
  },
>(todos: T[]): T[] {
  const porAula = new Map<string, T>()
  for (const exercise of todos) {
    const key = `${exercise.course_slug}:${exercise.lesson_number}`
    const current = porAula.get(key)
    if (!current || exercise.position < current.position) porAula.set(key, exercise)
  }
  return [...porAula.values()].sort(
    (a, b) =>
      a.course_slug.localeCompare(b.course_slug) || a.lesson_number - b.lesson_number,
  )
}

export function TestPage() {
  const { courseSlug = DEFAULT_COURSE_SLUG, unitSlug = '' } = useParams()
  return (
    <TestPageContent
      key={`${courseSlug}/${unitSlug}`}
      courseSlug={courseSlug}
      unitSlug={unitSlug}
    />
  )
}

function TestPageContent({
  courseSlug,
  unitSlug,
}: {
  courseSlug: string
  unitSlug: string
}) {
  const { usuario } = useSessao()
  const exercises = useAllExercises(courseSlug, unitSlug)
  const curriculum = useCourseCurriculum(courseSlug)
  const [answered, setAnswered] = useState<Record<number, boolean>>({})

  const questions = useMemo(
    () =>
      exercises.data
        ? umaPorAula(
            exercises.data.filter(
              (exercise) =>
                exercise.course_slug === courseSlug && exercise.unit_slug === unitSlug,
            ),
          )
        : [],
    [courseSlug, exercises.data, unitSlug],
  )

  if (!usuario) return null
  if (exercises.isPending || curriculum.isPending) return <Carregando oque="a avaliação" />
  if (exercises.error) {
    return <Erro erro={exercises.error} aoTentarDeNovo={() => void exercises.refetch()} />
  }
  if (curriculum.error) {
    return <Erro erro={curriculum.error} aoTentarDeNovo={() => void curriculum.refetch()} />
  }

  const unit = curriculum.data.units.find((candidate) => candidate.slug === unitSlug)
  if (!unit) {
    return (
      <div className="estado-erro" role="alert">
        <p>Esta unidade não existe neste curso.</p>
        <Link className="btn ghost" to={coursePath(courseSlug)}>
          Ver unidades
        </Link>
      </div>
    )
  }

  const correct = Object.values(answered).filter(Boolean).length
  const completed = Object.keys(answered).length

  return (
    <>
      <p className="eyebrow">
        Avaliação · {curriculum.data.course.title} · {unit.title}
      </p>
      <h1>Avaliação da unidade</h1>
      <p className="lead">
        Uma questão de cada aula desta unidade. O número ao lado indica a origem para você retomar
        o conteúdo quando necessário. A correção é feita pelo servidor.
      </p>

      {questions.length > 0 ? (
        <div className="stack tight" style={{ marginTop: 26 }}>
          {questions.map((question, index) => (
            <div key={question.id}>
              <p className="origem">Aula {question.lesson_number}</p>
              <ExerciseCard
                exercicio={question}
                numero={index + 1}
                userId={usuario.id}
                aoResponder={(ok) =>
                  setAnswered((current) => ({ ...current, [question.id]: ok }))
                }
              />
            </div>
          ))}
        </div>
      ) : (
        <div className="media-fallback" role="note">
          <h2>Avaliação em preparação</h2>
          <p>Esta unidade ainda não possui exercícios publicados para montar a avaliação.</p>
          <Link className="btn ghost" to={unitPath(courseSlug, unitSlug)}>
            Voltar à unidade
          </Link>
        </div>
      )}

      {questions.length > 0 && (
        <p className="score" role="status">
          <span className="n">
            {correct}/{questions.length}
          </span>
          <span className="lbl">
            {completed === 0
              ? 'nenhuma respondida ainda'
              : `acertos em ${completed} respondidas`}
          </span>
        </p>
      )}
    </>
  )
}
