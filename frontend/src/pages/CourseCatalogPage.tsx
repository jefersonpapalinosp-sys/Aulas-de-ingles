import { Link } from 'react-router-dom'
import { useCourses } from '../api/queries'
import { Carregando, Erro } from '../components/States'
import { coursePath } from '../routing/courseRoutes'

function statusLabel(status: string): string {
  if (status === 'published') return 'Publicado'
  if (status === 'planned') return 'Em preparação'
  if (status === 'archived') return 'Arquivado'
  return status
}

export function CourseCatalogPage() {
  const courses = useCourses()

  if (courses.isPending) return <Carregando oque="o catálogo de cursos" />
  if (courses.error) {
    return <Erro erro={courses.error} aoTentarDeNovo={() => void courses.refetch()} />
  }

  return (
    <section className="course-catalog" aria-labelledby="courses-title">
      <p className="eyebrow">Catálogo</p>
      <h1 id="courses-title">Cursos de inglês</h1>
      <p className="lead">
        Escolha um nível para ver as unidades, acompanhar seu progresso e retomar a aula certa.
      </p>
      <div className="course-card-grid">
        {courses.data.map((course) => (
          <article className="course-card" key={course.id}>
            <div>
              <p className="course-card-level">
                {course.level} · {course.proficiency_label}
              </p>
              <h2>{course.title}</h2>
              <p>{course.provider}</p>
            </div>
            <dl>
              <div>
                <dt>Aulas disponíveis</dt>
                <dd>
                  {course.published_lessons}/{course.total_lessons}
                </dd>
              </div>
              <div>
                <dt>Estado</dt>
                <dd>{statusLabel(course.status)}</dd>
              </div>
            </dl>
            <div className="course-card-actions">
              <Link className="btn" to={coursePath(course.slug)}>
                Ver unidades
              </Link>
              <a href={course.source_url} target="_blank" rel="noopener noreferrer">
                Fonte oficial ↗
              </a>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
