import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { useCourseCompletion } from '../api/completion'
import type { CourseCompletion } from '../api/client'
import { Carregando, Erro } from '../components/States'
import { coursePath, DEFAULT_COURSE_SLUG } from '../routing/courseRoutes'

type DiagnosticChoice = 'yes' | 'partial' | 'not_yet'
type DiagnosticQuestionId = 'listening' | 'language' | 'review'

const diagnosticQuestions: ReadonlyArray<{
  id: DiagnosticQuestionId
  prompt: string
}> = [
  {
    id: 'listening',
    prompt: 'Consigo acompanhar a ideia principal de um diálogo curto sem ler tudo?',
  },
  {
    id: 'language',
    prompt: 'Consigo falar ou escrever sobre experiências usando estruturas já estudadas?',
  },
  {
    id: 'review',
    prompt: 'Consigo perceber quando preciso revisar vocabulário, gramática ou listening?',
  },
]

const diagnosticChoices: ReadonlyArray<{
  value: DiagnosticChoice
  label: string
}> = [
  { value: 'yes', label: 'Sim' },
  { value: 'partial', label: 'Em parte' },
  { value: 'not_yet', label: 'Ainda não' },
]

function completionStatusLabel(status: CourseCompletion['progress']['status']): string {
  if (status === 'completed') return 'Aulas publicadas concluídas'
  if (status === 'in_progress') return 'Em andamento'
  return 'Ainda não iniciado'
}

function levelLabel(level: string): string {
  const normalized = level.trim()
  return /^level\b/i.test(normalized) ? normalized : `Level ${normalized}`
}

function courseStatusLabel(status: NonNullable<CourseCompletion['next_course']>['status']): string {
  if (status === 'published') return 'Disponível'
  if (status === 'planned') return 'Em preparação'
  return 'Arquivado'
}

function skillStatusLabel(status: CourseCompletion['skills'][number]['status']): string {
  if (status === 'strong') return 'Consistente'
  if (status === 'steady') return 'Estável'
  if (status === 'developing') return 'Em desenvolvimento'
  return 'Dados insuficientes'
}

function CourseSummary({ data }: { data: CourseCompletion }) {
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

function IncompleteWork({ data }: { data: CourseCompletion }) {
  const { incomplete_units: incompleteUnits, checkpoints } = data

  return (
    <div className="completion-two-column">
      <section className="completion-panel" aria-labelledby="incomplete-units-title">
        <p className="eyebrow">Aulas</p>
        <h2 id="incomplete-units-title">Unidades para continuar</h2>
        {incompleteUnits.length === 0 ? (
          <p className="completion-positive" role="status">
            Todas as unidades publicadas têm suas aulas concluídas.
          </p>
        ) : (
          <ul className="completion-link-list">
            {incompleteUnits.map((unit) => (
              <li key={unit.slug}>
                <Link to={unit.href}>
                  <strong>{unit.title}</strong>
                  <span>
                    {unit.completed_lessons}/{unit.published_lessons} concluídas ·{' '}
                    {unit.viewed_lessons} vistas
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
        <p className="completion-preserved-access">
          Estas unidades continuam acessíveis para estudo e revisão.
        </p>
      </section>

      <section className="completion-panel" aria-labelledby="pending-checkpoints-title">
        <p className="eyebrow">Revisões do recorte</p>
        <h2 id="pending-checkpoints-title">Checkpoints atuais</h2>
        <p className="completion-panel-summary">
          {checkpoints.current_completed} de {checkpoints.published} realizados na versão
          atual.
        </p>
        {checkpoints.pending.length > 0 ? (
          <ul className="completion-link-list">
            {checkpoints.pending.map((checkpoint) => (
              <li key={`${checkpoint.unit_slug}-${checkpoint.content_version}`}>
                <Link to={checkpoint.href}>
                  <strong>{checkpoint.title}</strong>
                  <span>Versão atual {checkpoint.content_version} · fazer checkpoint</span>
                </Link>
              </li>
            ))}
          </ul>
        ) : checkpoints.published > 0 ? (
          <p className="completion-positive" role="status">
            Todos os checkpoints publicados foram realizados na versão atual.
          </p>
        ) : (
          <p className="muted">Ainda não há checkpoints publicados neste curso.</p>
        )}
      </section>
    </div>
  )
}

function SkillsEvidence({ data }: { data: CourseCompletion }) {
  return (
    <section className="completion-skills" aria-labelledby="completion-skills-title">
      <p className="eyebrow">Evidências de prática</p>
      <h2 id="completion-skills-title">Competências observadas</h2>
      <p className="completion-section-intro">
        Competência não é calculada pelas aulas vistas. Ela resume tentativas registradas
        em exercícios, práticas de fala e feedbacks de escrita; checkpoints aparecem
        separadamente. São necessárias pelo menos três amostras para mostrar uma tendência.
      </p>

      {data.skills.length === 0 ? (
        <p className="completion-empty-copy" role="status">
          Ainda não há evidências de competência para resumir.
        </p>
      ) : (
        <ul className="completion-skill-list">
          {data.skills.map((skill) => {
            const insufficient = skill.samples < 3 || skill.score_percent === null
            return (
              <li key={skill.skill}>
                <div>
                  <strong>{skill.label}</strong>
                  <span>{skill.samples} {skill.samples === 1 ? 'evidência' : 'evidências'}</span>
                </div>
                {insufficient ? (
                  <span className="completion-skill-state insufficient">
                    Dados insuficientes ({skill.samples}/3)
                  </span>
                ) : (
                  <span className={`completion-skill-state ${skill.status}`}>
                    {skillStatusLabel(skill.status)} · {skill.score_percent}%
                  </span>
                )}
                {skill.fragile_topics.length > 0 && (
                  <p>Pontos para revisar: {skill.fragile_topics.join(', ')}.</p>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

function CertificateStatus({ data }: { data: CourseCompletion }) {
  const certificate = data.certificate
  const externalCertificate = /^https?:\/\//i.test(certificate.cta_href)
  return (
    <section
      className={`completion-certificate ${certificate.status}`}
      id="certificado"
      aria-labelledby="certificate-title"
      tabIndex={-1}
    >
      <p className="eyebrow">Elegibilidade</p>
      <h2 id="certificate-title">
        Certificado do recorte: {certificate.eligible ? 'elegível' : 'ainda não elegível'}
      </h2>
      <p>{certificate.reason}</p>
      <p className="completion-certificate-rule">
        Regra deste recorte: {certificate.required_lessons} aulas e{' '}
        {certificate.required_checkpoints} checkpoints atuais.
      </p>
      <p className="completion-no-download">
        Esta tela informa a elegibilidade. Nenhum certificado é baixado automaticamente.
      </p>
      {externalCertificate && (
        <p className="completion-no-download">
          Esta regra vale para o escopo “{certificate.scope_label}” dentro do aplicativo.
          A página externa da VOA considera o curso oficial completo e possui critérios
          próprios.
        </p>
      )}
      {externalCertificate ? (
        <a
          className="btn"
          href={certificate.cta_href}
          target="_blank"
          rel="noreferrer"
        >
          {certificate.cta_label}
        </a>
      ) : (
        <Link className="btn" to={certificate.cta_href}>
          {certificate.cta_label}
        </Link>
      )}
    </section>
  )
}

function Diagnostic({ data }: { data: CourseCompletion }) {
  const nextCourse = data.next_course
  const [answers, setAnswers] = useState<Partial<Record<DiagnosticQuestionId, DiagnosticChoice>>>(
    {},
  )
  const [showGuidance, setShowGuidance] = useState(false)
  const guidanceHeading = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    if (showGuidance) guidanceHeading.current?.focus()
  }, [showGuidance])

  if (!nextCourse) return null

  const nextLevel = nextCourse.level
  const nextLevelLabel = levelLabel(nextLevel)
  const currentLevelLabel = levelLabel(data.course.level)
  const complete = diagnosticQuestions.every((question) => answers[question.id])
  const values = diagnosticQuestions.map((question) => answers[question.id])
  const hasNotYet = values.includes('not_yet')
  const allYes = values.every((value) => value === 'yes')

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (complete) setShowGuidance(true)
  }

  function guidance() {
    if (allYes) {
      return {
        title: `Você pode explorar ${nextLevelLabel} agora`,
        copy: `Mantenha revisões curtas do ${currentLevelLabel} enquanto conhece o próximo nível.`,
      }
    }
    if (hasNotYet) {
      return {
        title: 'Revise no seu ritmo antes ou em paralelo',
        copy: `Retome os pontos sinalizados e explore ${nextLevelLabel} quando quiser. O próximo nível continua opcional.`,
      }
    }
    return {
      title: `Explore ${nextLevelLabel} mantendo revisões`,
      copy: 'Você pode conhecer o próximo nível e reforçar os pontos em que respondeu “Em parte”.',
    }
  }

  const result = guidance()

  return (
    <section
      className="completion-diagnostic"
      id="diagnostico"
      aria-labelledby="diagnostic-title"
      tabIndex={-1}
    >
      <p className="eyebrow">Autoavaliação curta · antes do próximo nível</p>
      <h2 id="diagnostic-title">{nextCourse.diagnostic.title}</h2>
      <p>{nextCourse.diagnostic.description}</p>
      <p className="completion-diagnostic-disclaimer">
        Esta autoavaliação não é prova, não gera nota e não altera seu progresso.
      </p>

      <form onSubmit={submit}>
        {diagnosticQuestions.map((question, questionIndex) => (
          <fieldset key={question.id}>
            <legend>
              <span>{questionIndex + 1}</span>
              {question.prompt}
            </legend>
            <div className="completion-diagnostic-options">
              {diagnosticChoices.map((choice) => (
                <label key={choice.value}>
                  <input
                    type="radio"
                    name={`diagnostic-${question.id}`}
                    value={choice.value}
                    checked={answers[question.id] === choice.value}
                    onChange={() => {
                      setAnswers((current) => ({ ...current, [question.id]: choice.value }))
                      setShowGuidance(false)
                    }}
                  />
                  <span>{choice.label}</span>
                </label>
              ))}
            </div>
          </fieldset>
        ))}
        <button className="btn" type="submit" disabled={!complete}>
          Ver orientação
        </button>
      </form>

      {showGuidance && (
        <div className="completion-diagnostic-result" role="status" aria-live="polite">
          <h3 ref={guidanceHeading} tabIndex={-1}>
            {result.title}
          </h3>
          <p>{result.copy}</p>
          <div className="completion-actions">
            <Link className="btn" to={nextCourse.href}>
              Conhecer {nextLevelLabel}
            </Link>
            <Link
              className="btn ghost"
              to={data.incomplete_units[0]?.href ?? coursePath(data.course.slug)}
            >
              Revisar {currentLevelLabel}
            </Link>
          </div>
        </div>
      )}
    </section>
  )
}

function NextCourse({ data }: { data: CourseCompletion }) {
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
