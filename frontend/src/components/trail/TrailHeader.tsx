import type { CourseSummary } from '../../api/client'

/** Uma barra de progresso com rótulo e contagem. */
function Progresso({ label, feitas, total }: { label: string; feitas: number; total: number }) {
  return (
    <div className="prog">
      <div className="prog-top">
        <span>{label}</span>
        <span>{feitas}/{total}</span>
      </div>
      <div
        className="prog-bar"
        role="progressbar"
        aria-label={`Progresso das ${label.toLocaleLowerCase('pt-BR')}`}
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={feitas}
      >
        <span className="prog-fill" style={{ width: total ? `${(feitas / total) * 100}%` : '0%' }} />
      </div>
    </div>
  )
}

/** Cabeçalho da trilha: em que curso o aluno está e quanto já andou.
 *
 * As duas barras medem coisas diferentes de propósito — o curso inteiro e a
 * unidade aberta. Só a do curso diria pouco a quem está no meio de uma unidade.
 */
export function TrailHeader({
  courses, courseSlug, courseTitle, provider, onCourseChange,
  studiedInCourse, lessonsInCourse, studiedInUnit, lessonsInUnit,
}: {
  courses: CourseSummary[]
  courseSlug: string
  courseTitle?: string
  provider?: string
  onCourseChange: (courseSlug: string) => void
  studiedInCourse: number
  lessonsInCourse: number
  studiedInUnit: number
  lessonsInUnit: number
}) {
  return (
    <header className="trail-head">
      <label className="trail-course-select">
        <span>Curso</span>
        <select value={courseSlug} onChange={(event) => onCourseChange(event.target.value)}>
          {courses.map((course) => (
            <option key={course.id} value={course.slug}>{course.title}</option>
          ))}
        </select>
      </label>
      <p className="brand">{provider ?? 'Cursos de inglês'}</p>
      <h2>{courseTitle ?? 'Carregando curso…'}</h2>
      <div className="trail-progress-grid">
        <Progresso label="Aulas do curso" feitas={studiedInCourse} total={lessonsInCourse} />
        <Progresso label="Aulas da unidade" feitas={studiedInUnit} total={lessonsInUnit} />
      </div>
    </header>
  )
}
