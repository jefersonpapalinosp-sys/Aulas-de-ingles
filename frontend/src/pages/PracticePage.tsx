import { Link, useParams } from 'react-router-dom'
import { useSessao } from '../api/auth'
import { useLesson } from '../api/queries'
import { Carregando, Erro } from '../components/States'
import { PracticeRunner } from '../features/practice/PracticeRunner'
import {
  courseLevelLabel,
  DEFAULT_COURSE_SLUG,
  lessonPath,
  studyPath,
} from '../routing/courseRoutes'

export function PracticePage() {
  const { courseSlug = DEFAULT_COURSE_SLUG, numero } = useParams()
  const lessonNumber = Number(numero)
  const { usuario } = useSessao()
  const lesson = useLesson(courseSlug, lessonNumber)

  if (!Number.isInteger(lessonNumber)) {
    return <p className="erro">Número de aula inválido.</p>
  }
  if (!usuario) return null
  if (lesson.isPending) return <Carregando oque={`os exercícios da aula ${lessonNumber}`} />
  if (lesson.error) return <Erro erro={lesson.error} aoTentarDeNovo={() => void lesson.refetch()} />

  return (
    <article className="practice-page">
      <header className="practice-page-header">
        <div>
          <p className="eyebrow">
            {courseLevelLabel(courseSlug)} · Aula {lesson.data.number} · laboratório
          </p>
          <h1>{lesson.data.title}</h1>
          <p className="lead">
            Exercícios · {lesson.data.grammar_tag}
          </p>
        </div>
        <Link className="practice-back-link" to={lessonPath(courseSlug, lessonNumber)}>
          Voltar à aula
        </Link>
      </header>

      <nav className="practice-page-links" aria-label="Atalhos da aula">
        <Link to={studyPath(courseSlug, lessonNumber, 'estudar')}>Rever teoria</Link>
        <Link to={studyPath(courseSlug, lessonNumber, 'revisar')}>Escrita e speaking</Link>
      </nav>

      <PracticeRunner
        key={`${courseSlug}:${lessonNumber}`}
        courseSlug={courseSlug}
        lessonNumber={lessonNumber}
        lessonTitle={lesson.data.title}
        userId={usuario.id}
      />
    </article>
  )
}
