import { useEffect, useMemo, useState } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { useSessao } from '../api/auth'
import { useMarcarEstudada, useSalvarStudySession, useStudySession } from '../api/progress'
import { useLesson } from '../api/queries'
import { Carregando, Erro } from '../components/States'
import { ActiveStudyTime } from '../features/study-session/ActiveStudyTime'
import { StepContent } from '../features/study-session/StepContent'
import { StepNavigator } from '../features/study-session/StepNavigator'
import {
  isStudyStep,
  readStudyProgress,
  saveStudyProgress,
  STUDY_STEPS,
  type StudyStepSlug,
} from '../features/study-session/studyProgress'
import {
  courseLevelLabel,
  DEFAULT_COURSE_SLUG,
  lessonPath,
  studyPath,
} from '../routing/courseRoutes'

export function StudyPage() {
  const { courseSlug = DEFAULT_COURSE_SLUG, numero, etapa } = useParams()
  const lessonNumber = Number(numero)
  const navigate = useNavigate()
  const { usuario } = useSessao()
  const { data: lesson, isPending, error, refetch } = useLesson(courseSlug, lessonNumber)
  const marcarEstudada = useMarcarEstudada(courseSlug)
  const serverSession = useStudySession(
    courseSlug,
    lessonNumber,
    Boolean(usuario) && Number.isInteger(lessonNumber),
  )
  const {
    mutate: sincronizarSessao,
    isPending: sincronizando,
    isError: sincronizacaoFalhou,
    isSuccess: sincronizado,
  } = useSalvarStudySession(courseSlug, lessonNumber)
  const localRead = useMemo(
    () => readStudyProgress(usuario?.id ?? 0, courseSlug, lessonNumber),
    [usuario?.id, courseSlug, lessonNumber],
  )
  const stored = localRead.progress
  const [localSaved, setLocalSaved] = useState(true)
  const [completedSteps, setCompletedSteps] = useState<StudyStepSlug[]>(stored.completedSteps)
  const [resumeStep, setResumeStep] = useState<StudyStepSlug>(stored.currentStep)
  const [hydrated, setHydrated] = useState(false)

  useEffect(() => {
    setCompletedSteps(stored.completedSteps)
    setResumeStep(stored.currentStep)
    setHydrated(false)
  }, [stored])

  useEffect(() => {
    if (!usuario || serverSession.isPending || hydrated) return
    const remoto = serverSession.data?.updated_at ? serverSession.data : null
    const localMaisCompleto =
      remoto !== null && stored.completedSteps.length > remoto.completed_steps.length
    setCompletedSteps(
      [...new Set([...stored.completedSteps, ...(remoto?.completed_steps ?? [])])],
    )
    setResumeStep(localMaisCompleto || !remoto ? stored.currentStep : remoto.current_step)
    setHydrated(true)
  }, [usuario, serverSession.isPending, serverSession.data, stored, hydrated])

  useEffect(() => {
    if (!usuario || !hydrated || !Number.isInteger(lessonNumber) || !isStudyStep(etapa)) return
    setLocalSaved(saveStudyProgress(usuario.id, courseSlug, lessonNumber, {
      currentStep: etapa,
      completedSteps,
    }))
    sincronizarSessao({ current_step: etapa, completed_steps: completedSteps })
  }, [
    usuario,
    hydrated,
    courseSlug,
    lessonNumber,
    etapa,
    completedSteps,
    sincronizarSessao,
  ])

  useEffect(() => {
    if (!hydrated || !serverSession.data) return
    const confirmed = serverSession.data.completed_steps
    setCompletedSteps((local) => confirmed.every((step) => local.includes(step))
      ? local : [...new Set([...local, ...confirmed])])
  }, [hydrated, serverSession.data])

  if (!Number.isInteger(lessonNumber)) return <p className="erro">Número de aula inválido.</p>
  if (!usuario) return null
  if (!etapa) {
    if (serverSession.isPending || !hydrated) return <Carregando oque="seu ponto de retomada" />
    return <Navigate to={studyPath(courseSlug, lessonNumber, resumeStep)} replace />
  }
  if (!isStudyStep(etapa)) {
    return (
      <div className="estado-erro" role="alert">
        <p>Esta etapa de estudo não existe.</p>
        <Link className="btn ghost" to={studyPath(courseSlug, lessonNumber)}>
          Retomar a aula
        </Link>
      </div>
    )
  }
  if (isPending || serverSession.isPending || !hydrated) {
    return <Carregando oque={`a aula ${lessonNumber}`} />
  }
  if (error) return <Erro erro={error} aoTentarDeNovo={() => void refetch()} />

  const currentStep: StudyStepSlug = etapa
  const userId = usuario.id
  const stepIndex = STUDY_STEPS.findIndex((step) => step.slug === currentStep)
  const previous = STUDY_STEPS[stepIndex - 1]
  const next = STUDY_STEPS[stepIndex + 1]
  const isComplete = STUDY_STEPS.every((step) => completedSteps.includes(step.slug))

  function persist(currentStep: StudyStepSlug, completed: StudyStepSlug[]) {
    setLocalSaved(saveStudyProgress(userId, courseSlug, lessonNumber, {
      currentStep,
      completedSteps: completed,
    }))
  }

  function completeAndContinue() {
    const completed = completedSteps.includes(currentStep)
      ? completedSteps
      : [...completedSteps, currentStep]
    setCompletedSteps(completed)

    if (next) {
      persist(next.slug, completed)
      navigate(studyPath(courseSlug, lessonNumber, next.slug))
      window.scrollTo({ top: 0, behavior: 'smooth' })
      return
    }

    persist(currentStep, completed)
    marcarEstudada.mutate({ numero: lessonNumber, estudada: true })
  }

  function goBack() {
    if (!previous) return
    persist(previous.slug, completedSteps)
    navigate(studyPath(courseSlug, lessonNumber, previous.slug))
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <article className="study-workspace">
      <header className="study-header">
        <div>
          <p className="eyebrow">
            {courseLevelLabel(lesson.course_slug)} · Aula {lesson.number} · estudo guiado
          </p>
          <h1>{lesson.title}</h1>
          <p className="lead">
            <em>{lesson.title_pt}</em> · {lesson.grammar_tag}
          </p>
        </div>
        <Link
          className="study-overview-link"
          to={lessonPath(courseSlug, lesson.number)}
        >
          Ver aula completa
        </Link>
      </header>

      <div
        className="study-progress"
        role="progressbar"
        aria-label="Progresso da jornada"
        aria-valuemin={0}
        aria-valuemax={STUDY_STEPS.length}
        aria-valuenow={completedSteps.length}
      >
        <span style={{ width: `${(completedSteps.length / STUDY_STEPS.length) * 100}%` }} />
      </div>

      <StepNavigator
        courseSlug={courseSlug}
        lessonNumber={lessonNumber}
        currentStep={currentStep}
        completedSteps={completedSteps}
      />

      <div className="study-body">
        <ActiveStudyTime key={`${userId}:${lesson.id}`} userId={userId} lessonId={lesson.id} />
        <p className="study-step-label">
          Etapa {stepIndex + 1} de {STUDY_STEPS.length}
        </p>
        {localRead.warning && <p role="alert" className="erro">{localRead.warning}</p>}
        {!localSaved && <p role="alert" className="erro">Jornada não salva no navegador. Confira a sincronização antes de sair.</p>}
        <StepContent lesson={lesson} step={currentStep} userId={userId} />

        {isComplete && currentStep === 'revisar' && (
          <div className="study-finished" role="status" aria-label="Conclusão da jornada">
            <p className="study-kicker">Jornada concluída</p>
            <h2>
              Boa! Você percorreu as cinco etapas de {courseLevelLabel(lesson.course_slug)} · Aula{' '}
              {lesson.number}.
            </h2>
            <p>
              {marcarEstudada.isPending
                ? 'Salvando a conclusão…'
                : marcarEstudada.isError
                  ? 'Não foi possível marcar a aula na conta. Confira o estado de salvamento e tente novamente.'
                  : 'A aula foi marcada como estudada e as palavras do deck voltarão na fila de revisão.'}
            </p>
          </div>
        )}
      </div>

      <footer className="study-actions">
        {previous ? (
          <button type="button" className="btn ghost" onClick={goBack}>
            ← {previous.shortTitle}
          </button>
        ) : (
          <Link className="btn ghost" to={lessonPath(courseSlug, lesson.number)}>
            ← Sair da jornada
          </Link>
        )}
        <span className={`study-sync ${sincronizacaoFalhou ? 'failed' : ''}`} aria-live="polite">
          {sincronizando
            ? 'Sincronizando…'
            : sincronizacaoFalhou
              ? localSaved ? 'Salvo neste dispositivo; sincronização pendente.' : 'Progresso apenas nesta tela; salvamento não confirmado.'
              : sincronizado
                ? 'Progresso sincronizado.'
                : ''}
        </span>
        <button
          type="button"
          className="btn"
          onClick={completeAndContinue}
          disabled={marcarEstudada.isPending || (isComplete && !next && !marcarEstudada.isError)}
        >
          {next
            ? `Concluir e ir para ${next.shortTitle}`
            : isComplete && marcarEstudada.isError
              ? 'Tentar marcar novamente'
              : isComplete
                ? 'Concluída'
                : 'Concluir aula'}
        </button>
      </footer>
    </article>
  )
}
