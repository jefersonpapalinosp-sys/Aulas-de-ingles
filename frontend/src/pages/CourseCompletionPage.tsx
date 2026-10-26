import { useEffect, useRef } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { useCourseCompletion } from '../api/completion'
import { Carregando, Erro } from '../components/States'
import { CertificateStatus } from '../features/completion/CertificateStatus'
import { levelLabel } from '../features/completion/completionLabels'
import { IncompleteWork, SkillsEvidence } from '../features/completion/CompletionWork'
import { CourseSummary } from '../features/completion/CourseSummary'
import { Diagnostic } from '../features/completion/Diagnostic'
import { NextCourse } from '../features/completion/NextCourse'
import { coursePath, DEFAULT_COURSE_SLUG } from '../routing/courseRoutes'

export function CourseCompletionPage() {
  const { courseSlug = DEFAULT_COURSE_SLUG } = useParams()
  const location = useLocation()
  const completion = useCourseCompletion(courseSlug)
  const pageHeading = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    if (!completion.data) return
    const targetId = location.hash.replace(/^#/, '')
    const target = targetId ? document.getElementById(targetId) : pageHeading.current
    if (!target) return
    if (typeof target.scrollIntoView === 'function') target.scrollIntoView({ block: 'start' })
    target.focus({ preventScroll: true })
  }, [completion.data, location.hash])

  if (completion.isPending) return <Carregando oque="a conclusão do curso" />
  if (completion.error) {
    return <Erro erro={completion.error} aoTentarDeNovo={() => void completion.refetch()} />
  }

  const data = completion.data

  return (
    <article className="course-completion-page" aria-labelledby="course-completion-page-title">
      <header className="completion-header">
        <p className="eyebrow">
          Fechamento do recorte publicado · {levelLabel(data.course.level)} ·{' '}
          {data.course.proficiency_label}
        </p>
        <h1 ref={pageHeading} id="course-completion-page-title" tabIndex={-1}>
          Conclusão de {data.course.title}
        </h1>
        <p className="lead">
          Veja separadamente o conteúdo disponível, as aulas vistas, as aulas concluídas e
          as competências sustentadas por evidências. Nada aqui bloqueia seu acesso ao
          curso.
        </p>
        <Link className="completion-map-link" to={coursePath(data.course.slug)}>
          Voltar ao mapa do curso
        </Link>
      </header>

      {data.progress.published_lessons === 0 ? (
        <section className="completion-empty" aria-labelledby="completion-empty-title">
          <p className="eyebrow">Sem conteúdo publicado</p>
          <h2 id="completion-empty-title">Ainda não há aulas publicadas neste curso</h2>
          <p>
            Quando o conteúdo estiver disponível, esta página mostrará seu percurso. O
            catálogo e o mapa continuam acessíveis.
          </p>
          <div className="completion-actions">
            <Link className="btn" to={coursePath(data.course.slug)}>
              Ver mapa do curso
            </Link>
            <Link className="btn ghost" to="/cursos">
              Ver catálogo
            </Link>
          </div>
        </section>
      ) : (
        <>
          <CourseSummary data={data} />
          <IncompleteWork data={data} />
          <SkillsEvidence data={data} />
          <CertificateStatus data={data} />
          <NextCourse data={data} />
          <Diagnostic data={data} />
        </>
      )}
    </article>
  )
}
