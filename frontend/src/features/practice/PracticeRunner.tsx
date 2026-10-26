import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import {
  useActivePracticeSession,
  useCreatePracticeSession,
  usePracticeExercises,
  usePracticeSession,
  useUpdatePracticePosition,
} from '../../api/practice'
import { filtersFromSession, practiceOptions } from './filters'
import { PracticeEmpty, PracticeIntro } from './PracticeIntro'
import { PracticePosition } from './practicePosition'
import { PracticeQuestion } from './PracticeQuestion'
import { PracticeContentChanged, PracticeFailure, PracticeResume } from './PracticeResume'
import { PracticeSummary } from './PracticeSummary'
import { useQueuedAttempts } from './queuedAttempts'
import {
  PRACTICE_MODE_LABELS,
  type ExerciseActivityEvent,
  type PracticeFilters,
  type PracticeMode,
  type PracticeSession as PracticeSessionData,
} from './types'

type PracticeRunnerProps = {
  courseSlug: string
  lessonNumber: number
  lessonTitle: string
  userId: number
  variant?: 'full' | 'embedded'
  initialFilters?: PracticeFilters
  lockFilters?: boolean
}

/** Conduz uma sessão de prática: um portão por vez, uma questão por vez.
 *
 * A posição saiu daqui para `practicePosition.ts`, que é onde vivem o espelho
 * local, a reconciliação com a conta e a chave de idempotência reaproveitada.
 * Este componente decide qual tela mostrar e cuida do que é da tela: foco,
 * anúncio para leitor de tela e a fila offline de tentativas.
 */
export function PracticeRunner({
  courseSlug,
  lessonNumber,
  lessonTitle,
  userId,
  variant = 'full',
  initialFilters = {},
  lockFilters = false,
}: PracticeRunnerProps) {
  const [filters, setFilters] = useState<PracticeFilters>(() => initialFilters)
  const [mode, setMode] = useState<PracticeMode>('guided')
  const [sessionId, setSessionId] = useState<number | null>(null)
  const [resumeAccepted, setResumeAccepted] = useState(false)
  const [showSummary, setShowSummary] = useState(false)
  const [announcement, setAnnouncement] = useState('')
  const [online, setOnline] = useState(() => navigator.onLine)
  const questionRef = useRef<HTMLHeadingElement>(null)

  const allExercises = usePracticeExercises(courseSlug, lessonNumber)
  const filteredExercises = usePracticeExercises(courseSlug, lessonNumber, filters)
  const activeQuery = useActivePracticeSession(courseSlug, lessonNumber)
  const sessionQuery = usePracticeSession(sessionId, sessionId !== null)
  const createSession = useCreatePracticeSession(courseSlug, lessonNumber)
  const updatePosition = useUpdatePracticePosition()
  const refetchPracticeSession = sessionQuery.refetch
  const updatePracticePosition = updatePosition.mutateAsync

  const position = useMemo(
    () => new PracticePosition(userId, {
      save: updatePracticePosition,
      reload: async () => (await refetchPracticeSession()).data ?? null,
    }),
    [refetchPracticeSession, updatePracticePosition, userId],
  )
  const local = useSyncExternalStore(position.subscribe, position.snapshot)

  const session = sessionId !== null ? (sessionQuery.data ?? null) : null
  const attempts = useQueuedAttempts(session, userId, refetchPracticeSession)

  const activeSession = activeQuery.data ?? null
  const currentPosition = session ? (local.local ?? session.current_position) : 0
  const currentItem = session?.items.find((item) => item.position === currentPosition)
  const currentExerciseId = currentItem?.exercise.id
  const currentIndex = session?.items.findIndex((item) => item.position === currentPosition) ?? -1
  const currentQueued = currentItem ? attempts.queued.has(currentItem.exercise.id) : false
  const currentCompleted = currentItem ? currentItem.outcome !== 'pending' || currentQueued : false

  const options = useMemo(() => practiceOptions(allExercises.data ?? []), [allExercises.data])

  useEffect(() => () => { position.dispose() }, [position])

  useEffect(() => {
    const handleOnline = () => setOnline(true)
    const handleOffline = () => setOnline(false)
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  useEffect(() => {
    if (session) position.load(session)
  }, [position, session])

  useEffect(() => {
    if (session) void position.settle(session, online)
  }, [local.local, online, position, session])

  useEffect(() => {
    if (currentExerciseId === undefined || !resumeAccepted) return
    questionRef.current?.focus()
  }, [currentExerciseId, resumeAccepted])

  async function begin(
    selectedMode: PracticeMode = mode,
    sourceSessionId?: number,
    selectedFilters: PracticeFilters = filters,
  ) {
    attempts.clearError()
    try {
      const created = await createSession.mutateAsync({
        idempotency_key: crypto.randomUUID(),
        mode: selectedMode,
        ...(selectedFilters.activityType ? { activity_type: selectedFilters.activityType } : {}),
        ...(selectedFilters.skill ? { skill: selectedFilters.skill } : {}),
        ...(selectedFilters.objective ? { objective: selectedFilters.objective } : {}),
        ...(sourceSessionId ? { source_session_id: sourceSessionId } : {}),
      })
      setSessionId(created.id)
      setResumeAccepted(true)
      position.reset()
      attempts.forget()
      setShowSummary(created.status === 'completed')
      setAnnouncement(`${PRACTICE_MODE_LABELS[created.mode]} iniciada.`)
    } catch {
      void activeQuery.refetch()
    }
  }

  function acceptResume(sessionToResume: PracticeSessionData) {
    setSessionId(sessionToResume.id)
    setResumeAccepted(true)
    setShowSummary(false)
    setAnnouncement(`Sessão retomada na questão ${sessionToResume.current_position + 1}.`)
  }

  async function refreshAfterActivity(event: ExerciseActivityEvent) {
    if (event.type === 'attempt' && event.status === 'queued') {
      attempts.mark(event.exerciseId)
      return
    }
    if (event.type === 'hint') setAnnouncement(`Dica ${event.level} aberta.`)
    await sessionQuery.refetch()
  }

  async function moveTo(target: number) {
    if (!session || !session.items.some((item) => item.position === target)) return
    attempts.clearError()
    setAnnouncement(`Questão ${target + 1} de ${session.summary.total}.`)
    await position.moveTo(session, target, online)
  }

  if (activeQuery.isPending || allExercises.isPending) {
    return <p role="status">Carregando o laboratório de exercícios…</p>
  }

  if (activeQuery.error || allExercises.error) {
    return (
      <PracticeFailure
        title="Não foi possível abrir os exercícios"
        message={(activeQuery.error ?? allExercises.error)?.message}
        action="Tentar novamente"
        onRetry={() => { void activeQuery.refetch(); void allExercises.refetch() }}
      />
    )
  }

  if (!resumeAccepted && activeSession?.content_changed) {
    return (
      <PracticeContentChanged
        title="Os exercícios mudaram desde o início desta sessão"
        note="Seu histórico anterior continuará registrado. Comece uma sessão nova para não misturar versões do conteúdo."
        disabled={createSession.isPending || !online}
        onRestart={() => void begin('guided', undefined, filtersFromSession(activeSession))}
      />
    )
  }

  if (!resumeAccepted && activeSession) {
    return <PracticeResume session={activeSession} onResume={() => acceptResume(activeSession)} />
  }

  if (sessionId !== null && (sessionQuery.isPending || !session)) {
    if (sessionQuery.error) {
      return (
        <PracticeFailure
          title="Não foi possível retomar esta sessão"
          message={sessionQuery.error.message}
          action="Tentar novamente"
          onRetry={() => void sessionQuery.refetch()}
        />
      )
    }
    return <p role="status">Retomando sua sessão…</p>
  }

  if (session?.content_changed) {
    return (
      <PracticeContentChanged
        title="Esta sessão usa uma versão anterior dos exercícios"
        note="O histórico foi preservado, mas as respostas novas precisam usar a versão atual."
        disabled={createSession.isPending || !online}
        onRestart={() => void begin('guided', undefined, filtersFromSession(session))}
      />
    )
  }

  if (session && session.status === 'completed' && showSummary) {
    return (
      <PracticeSummary
        session={session}
        courseSlug={courseSlug}
        lessonNumber={lessonNumber}
        starting={createSession.isPending}
        onRepeatMistakes={() => void begin('mistakes', session.id, filtersFromSession(session))}
      />
    )
  }

  if (!session) {
    const total = allExercises.data?.length ?? 0
    if (total === 0) return <PracticeEmpty courseSlug={courseSlug} lessonNumber={lessonNumber} />
    return (
      <PracticeIntro
        lessonNumber={lessonNumber}
        variant={variant}
        lockFilters={lockFilters}
        mode={mode}
        onMode={setMode}
        filters={filters}
        onFilters={setFilters}
        options={options}
        total={total}
        filteredTotal={filteredExercises.data?.length ?? 0}
        filtering={filteredExercises.isPending}
        filterError={Boolean(filteredExercises.error)}
        online={online}
        starting={createSession.isPending}
        startError={createSession.isError ? createSession.error.message : ''}
        onStart={() => void begin()}
      />
    )
  }

  if (!currentItem || currentIndex < 0) {
    return (
      <PracticeFailure
        title="A posição salva não existe neste pack"
        message="Recarregue a sessão para voltar a uma questão válida."
        action="Recarregar sessão"
        onRetry={() => void sessionQuery.refetch()}
      />
    )
  }

  return (
    <PracticeQuestion
      session={session}
      index={currentIndex}
      item={currentItem}
      lessonTitle={lessonTitle}
      courseSlug={courseSlug}
      lessonNumber={lessonNumber}
      userId={userId}
      variant={variant}
      queued={currentQueued}
      queuedCount={attempts.queued.size}
      completed={currentCompleted}
      announcement={announcement}
      storageWarning={local.storageWarning}
      navigationError={local.error || attempts.error}
      navigating={updatePosition.isPending}
      questionRef={questionRef}
      onMove={(target) => void moveTo(target)}
      onSummary={() => setShowSummary(true)}
      onActivity={(event) => void refreshAfterActivity(event)}
    />
  )
}
