import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useProgress } from '../api/progress'
import { useCourseCurriculum } from '../api/queries'
import { Carregando, Erro } from '../components/States'
import { lessonProgressKey } from '../features/curriculum/curriculum'
import { TodayPanel } from '../features/plan/TodayPanel'
import {
  courseCompletionPath,
  coursePath,
  courseReviewPath,
  DEFAULT_COURSE_SLUG,
  lessonPath,
  unitPath,
} from '../routing/courseRoutes'

export function MapPage({ showToday = false }: { showToday?: boolean }) {
  const params = useParams()
  const [searchParams] = useSearchParams()
  const courseSlug =
    params.courseSlug ?? searchParams.get('course') ?? DEFAULT_COURSE_SLUG
  const unitSlug = params.unitSlug
  const curriculum = useCourseCurriculum(courseSlug)
  const progress = useProgress(courseSlug)

  if (curriculum.isPending) return <Carregando oque="o mapa do curso" />
  if (curriculum.error) {
    return (
      <Erro erro={curriculum.error} aoTentarDeNovo={() => void curriculum.refetch()} />
    )
  }
  if (progress.isPending) return <Carregando oque="o progresso deste curso" />
  if (progress.error) {
    return <Erro erro={progress.error} aoTentarDeNovo={() => void progress.refetch()} />
  }

  const studied = new Set(
    progress.data?.lessons
      .filter((lesson) => lesson.studied)
      .map((lesson) => lessonProgressKey(lesson.course_slug, lesson.lesson_number)) ?? [],
  )
  const selectedUnit = unitSlug
    ? curriculum.data.units.find((unit) => unit.slug === unitSlug)
    : undefined

  if (unitSlug && !selectedUnit) {
    return (
      <div className="estado-erro" role="alert">
        <p>Esta unidade não existe neste curso.</p>
        <Link className="btn ghost" to={coursePath(courseSlug)}>
          Ver unidades
        </Link>
      </div>
    )
  }

  return (
    <>
      {showToday && (
        <TodayPanel
          courseSlug={courseSlug}
          unitSlug={unitSlug}
        />
      )}
      <section
        className={showToday ? 'map-section course-map' : 'course-map'}
        aria-labelledby="map-title"
      >
        <p className="eyebrow">
          {curriculum.data.course.title} · {curriculum.data.course.proficiency_label} ·{' '}
          {curriculum.data.course.provider}
        </p>
        <div className="course-map-title">
          <div>
            <h1 id="map-title">
              {selectedUnit ? selectedUnit.title : 'Mapa do curso'}
            </h1>
            <p className="lead">
              {selectedUnit
                ? `${selectedUnit.published_lessons} aulas disponíveis${selectedUnit.review ? ' e um checkpoint de consolidação' : ''} nesta unidade.`
                : 'Abra uma unidade para ver uma lista curta de aulas e continuar sem percorrer o curso inteiro.'}
            </p>
          </div>
          {selectedUnit && (
            <Link to={coursePath(courseSlug)} className="btn ghost">
              Todas as unidades
            </Link>
          )}
        </div>

        <div className="unit-card-grid">
          {curriculum.data.units.map((unit) => {
            const completed = unit.lessons.filter((lesson) =>
              studied.has(lessonProgressKey(courseSlug, lesson.number)),
            ).length
            const state =
              unit.published_lessons === 0
                ? unit.status === 'planned'
                  ? 'Em preparação'
                  : 'Sem aulas publicadas'
                : completed === 0
                ? 'Não iniciada'
                : completed === unit.lessons.length
                  ? unit.review
                    ? 'Aulas concluídas · checkpoint disponível'
                    : 'Concluída'
                  : 'Em andamento'
            const content = (
              <>
                <span>
                  <strong>{unit.title}</strong>
                  <small>
                    Aulas {unit.lesson_start}–{unit.lesson_end}
                    {unit.review ? ' · checkpoint' : ''}
                  </small>
                </span>
                <span>
                  <small>{state}</small>
                  <strong>
                    {unit.published_lessons === 0
                      ? `${unit.total_lessons} ${unit.total_lessons === 1 ? 'aula planejada' : 'aulas planejadas'}`
                      : `${completed}/${unit.lessons.length} ${unit.lessons.length === 1 ? 'aula' : 'aulas'}`}
                  </strong>
                </span>
              </>
            )
            return unit.published_lessons === 0 ? (
              <article
                className="unit-card"
                key={unit.id}
                aria-disabled="true"
                aria-label={`${unit.title}: ${state}`}
              >
                {content}
              </article>
            ) : (
              <Link
                className={`unit-card${unit.slug === unitSlug ? ' active' : ''}`}
                key={unit.id}
                to={unitPath(courseSlug, unit.slug)}
                aria-current={unit.slug === unitSlug ? 'page' : undefined}
              >
                {content}
              </Link>
            )
          })}
        </div>

        {!selectedUnit &&
          curriculum.data.course.status === 'published' &&
          curriculum.data.course.published_lessons > 0 && (
            <section className="course-completion-entry" aria-labelledby="course-completion-title">
              <div>
                <p className="eyebrow">Fechamento do recorte publicado</p>
                <h2 id="course-completion-title">Conclusão do curso</h2>
                <p>
                  Confira separadamente o conteúdo disponível, as aulas concluídas e o
                  desempenho sustentado pelas suas evidências de estudo.
                </p>
              </div>
              <Link className="btn" to={courseCompletionPath(courseSlug)}>
                Ver meu fechamento
              </Link>
            </section>
          )}

        {selectedUnit && selectedUnit.published_lessons === 0 && (
          <div className="media-fallback" role="note">
            <h2>Unidade em preparação</h2>
            <p>
              As Aulas {selectedUnit.lesson_start}–{selectedUnit.lesson_end} ainda não estão
              publicadas. Elas aparecerão aqui quando o conteúdo estiver pronto para estudo.
            </p>
            <Link className="btn ghost" to={coursePath(courseSlug)}>
              Ver unidades disponíveis
            </Link>
          </div>
        )}

        {selectedUnit && selectedUnit.published_lessons > 0 && (
          <div className="arc course-unit-lessons">
            <div className="ahead">
              <span>Aula</span>
              <span>Título</span>
              <span>Foco gramatical</span>
              <span>Estado</span>
            </div>
            {selectedUnit.lessons.map((lesson) => {
              const isStudied = studied.has(lessonProgressKey(courseSlug, lesson.number))
              return (
                <Link
                  className="arow"
                  key={lesson.id}
                  to={lessonPath(courseSlug, lesson.number)}
                >
                  <span className="an">{lesson.number}</span>
                  <span className="at">{lesson.title}</span>
                  <span className="ag">{lesson.grammar_tag}</span>
                  <span className={`ap ${isStudied ? 'is-studied' : ''}`}>
                    {isStudied ? 'Estudada' : 'Pendente'}
                  </span>
                </Link>
              )
            })}
            {selectedUnit.review && (
              <Link
                className="arow checkpoint-map-row"
                to={courseReviewPath(courseSlug, selectedUnit.slug)}
              >
                <span className="an" aria-hidden="true">CP</span>
                <span className="at">{selectedUnit.review.title}</span>
                <span className="ag">
                  {selectedUnit.review.question_count} questões · cerca de{' '}
                  {selectedUnit.review.estimated_minutes} min
                </span>
                <span className="ap">Abrir</span>
              </Link>
            )}
          </div>
        )}
      </section>
    </>
  )
}
