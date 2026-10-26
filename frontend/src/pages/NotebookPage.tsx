import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { fetchPersonalExport, type NotebookScope } from '../api/notebook'
import { useCourseCurriculum, useCourses } from '../api/queries'
import { curriculumLessons } from '../features/curriculum/curriculum'
import { HistoricalEvidenceSection } from '../features/notebook/HistoricalEvidenceSection'
import { NotebookCompose } from '../features/notebook/NotebookCompose'
import { NotebookList } from '../features/notebook/NotebookList'
import { failureMessage } from '../features/notebook/labels'
import { SpeakingHistorySection } from '../features/notebook/SpeakingHistorySection'
import { WritingHistorySection } from '../features/notebook/WritingHistorySection'
import { DEFAULT_COURSE_SLUG } from '../routing/courseRoutes'

/**
 * Caderno privado do aluno.
 *
 * A página escolhe o escopo (curso e unidade, na URL) e cede cada seção ao
 * seu componente; os dados de cada uma vivem em `api/notebook.ts`. A mensagem
 * de status é uma só, no topo, porque as ações ficam espalhadas pelas seções e
 * o aluno precisa de um único lugar para olhar depois de agir.
 */
export function NotebookPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const courseSlug = searchParams.get('course') || DEFAULT_COURSE_SLUG
  const unitSlug = searchParams.get('unit') || ''
  const scope: NotebookScope = useMemo(
    () => ({ courseSlug, unitSlug: unitSlug || undefined }),
    [courseSlug, unitSlug],
  )
  const courses = useCourses()
  const curriculum = useCourseCurriculum(courseSlug)
  const lessons = useMemo(
    () =>
      curriculumLessons(curriculum.data).filter(
        (lesson) => !unitSlug || lesson.unit_slug === unitSlug,
      ),
    [curriculum.data, unitSlug],
  )
  const [message, setMessage] = useState('')
  const [exporting, setExporting] = useState(false)

  function setScope(nextCourse: string, nextUnit = '') {
    const next = new URLSearchParams(searchParams)
    next.set('course', nextCourse)
    if (nextUnit) next.set('unit', nextUnit)
    else next.delete('unit')
    setSearchParams(next, { replace: true })
    setMessage('')
  }

  async function exportData() {
    setExporting(true)
    setMessage('')
    try {
      const url = URL.createObjectURL(await fetchPersonalExport())
      const link = document.createElement('a')
      link.href = url
      link.download = 'aulas-ingles-dados.json'
      link.click()
      URL.revokeObjectURL(url)
      setMessage('Exportação preparada. Confira os downloads do navegador.')
    } catch (error) {
      setMessage(failureMessage(error, 'Não foi possível exportar seus dados agora.'))
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="notebook-page">
      <header className="notebook-header">
        <div>
          <p className="eyebrow">Seu espaço privado</p>
          <h1>Caderno de inglês</h1>
        </div>
        <button
          type="button"
          className="btn ghost"
          disabled={exporting}
          onClick={() => void exportData()}
        >
          {exporting ? 'Exportando…' : 'Exportar meus dados'}
        </button>
      </header>
      <p className="notebook-privacy">
        As anotações são privadas e não alteram as aulas.
        {' '}<Link to="/meus-dados">Meus dados e áudios</Link>
      </p>
      <div className="notebook-filters" aria-label="Escopo do caderno">
        <label>
          Curso
          <select value={courseSlug} onChange={(event) => setScope(event.target.value)}>
            {(courses.data ?? []).map((course) => (
              <option key={course.slug} value={course.slug}>
                {course.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          Unidade
          <select
            value={unitSlug}
            onChange={(event) => setScope(courseSlug, event.target.value)}
          >
            <option value="">Todas as unidades</option>
            {(curriculum.data?.units ?? []).map((unit) => (
              <option key={unit.slug} value={unit.slug}>
                {unit.title}
              </option>
            ))}
          </select>
        </label>
      </div>
      {message && <p className="notebook-message" role="status">{message}</p>}

      {/* O rascunho em digitação sobrevive a uma troca de escopo, então o
          compositor não remonta. A lista, sim: os filtros de aula e tipo e a
          edição em curso pertencem ao recorte que acabou de sair. */}
      <NotebookCompose scope={scope} lessons={lessons} onMessage={setMessage} />
      <NotebookList
        key={`${courseSlug}:${unitSlug}`}
        scope={scope}
        lessons={lessons}
        onMessage={setMessage}
      />
      <WritingHistorySection scope={scope} />
      <SpeakingHistorySection scope={scope} onMessage={setMessage} />
      <HistoricalEvidenceSection />
    </div>
  )
}
