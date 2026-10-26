import { Link } from 'react-router-dom'
import type { CourseCompletion } from '../../api/client'
import { courseStatusLabel, levelLabel } from './completionLabels'

export function NextCourse({ data }: { data: CourseCompletion }) {
  const nextCourse = data.next_course

  if (!nextCourse) {
    return (
      <section className="completion-next-course" aria-labelledby="next-course-title">
        <p className="eyebrow">Próximo passo</p>
        <h2 id="next-course-title">Continue pelo catálogo</h2>
        <p>Não há outro nível indicado neste catálogo no momento.</p>
        <Link className="btn ghost" to="/cursos">
          Ver catálogo de cursos
        </Link>
      </section>
    )
  }

  const nextLevelLabel = levelLabel(nextCourse.level)

  return (
    <section className="completion-next-course" aria-labelledby="next-course-title">
      <div>
        <p className="eyebrow">Próximo nível</p>
        <h2 id="next-course-title">{nextCourse.title}</h2>
        <p className="completion-next-meta">
          {nextLevelLabel} · {nextCourse.proficiency_label} ·{' '}
          {courseStatusLabel(nextCourse.status)}
        </p>
        <p>{nextCourse.preview}</p>
        <p className="completion-optional">
          <strong>Recomendado e opcional.</strong> Você pode continuar revisando este curso e
          conhecer o próximo nível no seu ritmo.
        </p>
      </div>
      <div className="completion-actions">
        <Link className="btn" to={nextCourse.href}>
          Conhecer {nextLevelLabel}
        </Link>
        <Link className="btn ghost" to={nextCourse.diagnostic.href}>
          Fazer autoavaliação antes
        </Link>
      </div>
    </section>
  )
}
