import type { CourseCompletion } from '../../api/client'
import { completionStatusLabel } from './completionLabels'

export function CourseSummary({ data }: { data: CourseCompletion }) {
  const { progress, checkpoints } = data
  const completionPercent = Math.min(100, Math.max(0, progress.completion_percent))

  return (
    <section className="completion-overview" aria-labelledby="completion-overview-title">
      <div className="completion-section-heading">
        <div>
          <p className="eyebrow">O que cada número representa</p>
          <h2 id="completion-overview-title">Seu percurso no conteúdo publicado</h2>
        </div>
        <span className={`completion-status ${progress.status}`}>
          {completionStatusLabel(progress.status)}
        </span>
      </div>

      <dl className="completion-metrics">
        <div>
          <dt>Conteúdo publicado</dt>
          <dd>{progress.published_lessons}</dd>
          <dd className="completion-metric-definition">
            Aulas disponíveis neste recorte do curso.
          </dd>
        </div>
        <div>
          <dt>Aulas vistas</dt>
          <dd>
            {progress.viewed_lessons}
            <span> / {progress.published_lessons}</span>
          </dd>
          <dd className="completion-metric-definition">
            Sessão de estudo iniciada ou aula marcada como estudada.
          </dd>
        </div>
        <div>
          <dt>Aulas concluídas</dt>
          <dd>
            {progress.completed_lessons}
            <span> / {progress.published_lessons}</span>
          </dd>
          <dd className="completion-metric-definition">
            Somente aulas marcadas como estudadas.
          </dd>
        </div>
        <div>
          <dt>Checkpoints atuais</dt>
          <dd>
            {checkpoints.current_completed}
            <span> / {checkpoints.published}</span>
          </dd>
          <dd className="completion-metric-definition">
            Tentativas feitas na versão publicada atual.
          </dd>
        </div>
      </dl>

      <div className="completion-progress-copy">
        <span id="completion-progress-label">Aulas concluídas no recorte publicado</span>
        <strong>{completionPercent}%</strong>
      </div>
      <div
        className="completion-progress"
        role="progressbar"
        aria-labelledby="completion-progress-label"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={completionPercent}
      >
        <span style={{ width: `${completionPercent}%` }} />
      </div>
    </section>
  )
}
