import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import type { Exercise } from '../../api/client'
import {
  useActivePracticeSession,
  useCreatePracticeSession,
  usePracticeExercises,
  usePracticeSession,
  useUpdatePracticePosition,
} from '../../api/practice'
import { ExerciseCard } from '../../components/ExerciseCard'
import {
  ATTEMPT_QUEUE_EVENT,
  ATTEMPT_QUEUE_SYNC_EVENT,
  listPendingAttempts,
  type AttemptQueueChangeEventDetail,
  type AttemptQueueSyncEventDetail,
} from '../offline/attemptQueue'
import { lessonPath, studyPath } from '../../routing/courseRoutes'
import {
  ACTIVITY_TYPE_LABELS,
  PRACTICE_MODE_LABELS,
  PRACTICE_OBJECTIVE_LABELS,
  SKILL_LABELS,
  type ExerciseActivityEvent,
  type PracticeActivityType,
  type PracticeFilters,
  type PracticeMode,
  type PracticeObjective,
  type PracticeSession as PracticeSessionData,
  type PracticeSkill,
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

function localPositionKey(userId: number, sessionId: number): string {
  return `aulas-ingles:practice-position:v1:${userId}:${sessionId}`
}

function readLocalPosition(userId: number, session: PracticeSessionData): number | null {
  try {
    const raw = localStorage.getItem(localPositionKey(userId, session.id))
    if (raw === null) return null
    const position = Number(raw)
    return session.items.some((item) => item.position === position) ? position : null
  } catch {
    return null
  }
}

function writeLocalPosition(userId: number, sessionId: number, position: number | null) {
  try {
    const key = localPositionKey(userId, sessionId)
    if (position === null) localStorage.removeItem(key)
    else localStorage.setItem(key, String(position))
  } catch {
    // A sessão continua utilizável mesmo quando o navegador bloqueia o storage.
  }
}

function unique(values: Array<string | null | undefined>): string[] {
  return [...new Set(values.filter((value): value is string => Boolean(value)))].sort()
}

function activityLabel(value: string): string {
  return ACTIVITY_TYPE_LABELS[value] ?? value.replaceAll('_', ' ')
}

function objectiveOf(exercise: Exercise): PracticeObjective | null {
  return exercise.objective
}

function filtersFromSession(session: PracticeSessionData): PracticeFilters {
  const activityType =
    session.activity_type && session.activity_type in ACTIVITY_TYPE_LABELS
      ? (session.activity_type as PracticeActivityType)
      : undefined
  const skill =
    session.skill && session.skill in SKILL_LABELS
      ? (session.skill as PracticeSkill)
      : undefined
  return {
    activityType,
    skill,
    objective: session.objective ?? undefined,
  }
}

function modeDescription(mode: PracticeMode): string {
  if (mode === 'quick') return 'Cinco questões escolhidas em ordem estável, sem cronômetro.'
  if (mode === 'mistakes') return 'Uma nova sessão apenas com os itens frágeis desta tentativa.'
  return 'Todos os itens do recorte, com dicas progressivas e explicação.'
}

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
  const [localPosition, setLocalPosition] = useState<number | null>(null)
  const [queuedExercises, setQueuedExercises] = useState<Set<number>>(() => new Set())
  const [showSummary, setShowSummary] = useState(false)
  const [announcement, setAnnouncement] = useState('')
  const [navigationError, setNavigationError] = useState('')
  const [online, setOnline] = useState(() => navigator.onLine)
  const questionRef = useRef<HTMLHeadingElement>(null)
  const positionSyncingRef = useRef(false)

  const allExercises = usePracticeExercises(courseSlug, lessonNumber)
  const filteredExercises = usePracticeExercises(courseSlug, lessonNumber, filters)
  const activeQuery = useActivePracticeSession(courseSlug, lessonNumber)
  const sessionQuery = usePracticeSession(sessionId, sessionId !== null)
  const createSession = useCreatePracticeSession(courseSlug, lessonNumber)
  const updatePosition = useUpdatePracticePosition()
  const refetchPracticeSession = sessionQuery.refetch
  const updatePracticePosition = updatePosition.mutateAsync

  const activeSession = activeQuery.data ?? null
  const session = sessionId !== null ? (sessionQuery.data ?? null) : null
  const currentPosition = session ? (localPosition ?? session.current_position) : 0
  const currentItem = session?.items.find((item) => item.position === currentPosition)
  const currentExerciseId = currentItem?.exercise.id
  const currentIndex = session?.items.findIndex((item) => item.position === currentPosition) ?? -1
  const currentQueued = currentItem ? queuedExercises.has(currentItem.exercise.id) : false
  const currentCompleted = currentItem
    ? currentItem.outcome !== 'pending' || currentQueued
    : false

  const options = useMemo(() => {
    const exercises = allExercises.data ?? []
    return {
      activityTypes: unique(
        exercises.map((exercise) => exercise.activity_type),
      ) as PracticeActivityType[],
      skills: unique(exercises.map((exercise) => exercise.skill)) as PracticeSkill[],
      objectives: unique(exercises.map(objectiveOf)) as PracticeObjective[],
    }
  }, [allExercises.data])

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
    if (!session) return
    setLocalPosition(readLocalPosition(userId, session))
  }, [session, userId])

  useEffect(() => {
    if (!session) return
    const refreshQueued = (event?: Event) => {
      const reason = (event as CustomEvent<AttemptQueueChangeEventDetail> | undefined)?.detail
        ?.reason
      // Durante o sync, o card continua bloqueado como "Na fila" até o GET da
      // sessão confirmar a correção. Assim não existe uma janela para enviar
      // uma segunda tentativa enquanto várias entradas são processadas.
      if (reason === 'synced' || reason === 'blocked') return
      setQueuedExercises(
        new Set(
          listPendingAttempts(userId)
            .filter((attempt) => attempt.sessionId === session.id)
            .map((attempt) => attempt.exerciseId),
        ),
      )
    }
    refreshQueued()
    window.addEventListener(ATTEMPT_QUEUE_EVENT, refreshQueued)
    return () => window.removeEventListener(ATTEMPT_QUEUE_EVENT, refreshQueued)
  }, [session, userId])

  useEffect(() => {
    if (currentExerciseId === undefined || !resumeAccepted) return
    questionRef.current?.focus()
  }, [currentExerciseId, resumeAccepted])

  const reconcilePosition = useCallback(
    async (position: number, baseline: PracticeSessionData): Promise<boolean> => {
      if (positionSyncingRef.current) return false
      positionSyncingRef.current = true
      const idempotencyKey = crypto.randomUUID()
      try {
        try {
          await updatePracticePosition({
            sessionId: baseline.id,
            currentPosition: position,
            expectedRevision: baseline.state_revision,
            idempotencyKey,
          })
        } catch (initialError) {
          const { data: latest } = await refetchPracticeSession()
          if (!latest || latest.id !== baseline.id) throw initialError

          if (latest.current_position !== position) {
            if (latest.status !== 'active' || latest.content_changed) throw initialError
            await updatePracticePosition({
              sessionId: latest.id,
              currentPosition: position,
              expectedRevision: latest.state_revision,
              // A mesma chave cobre tanto uma revisão concorrente quanto uma
              // resposta perdida depois de o primeiro PUT ter sido aplicado.
              idempotencyKey,
            })
          }
        }
        writeLocalPosition(userId, baseline.id, null)
        setLocalPosition(null)
        setNavigationError('')
        return true
      } catch {
        setNavigationError(
          'A nova posição ficou salva neste dispositivo. Tentaremos sincronizar quando a sessão estiver disponível.',
        )
        return false
      } finally {
        positionSyncingRef.current = false
      }
    },
    [refetchPracticeSession, updatePracticePosition, userId],
  )

  useEffect(() => {
    if (!online || !session || localPosition === null) return
    if (session.current_position === localPosition) {
      writeLocalPosition(userId, session.id, null)
      setLocalPosition(null)
      setNavigationError('')
      return
    }
    void reconcilePosition(localPosition, session)
  }, [localPosition, online, reconcilePosition, session, userId])

  useEffect(() => {
    function handleSync(event: Event) {
      const detail = (event as CustomEvent<AttemptQueueSyncEventDetail>).detail
      if (!session || detail.userId !== userId) return
      const synced = detail.syncedAttempts.filter((attempt) => attempt.sessionId === session.id)
      const rejected = detail.rejectedAttempts.filter(
        (attempt) => attempt.sessionId === session.id,
      )
      if (synced.length === 0 && rejected.length === 0) return

      void refetchPracticeSession().finally(() => {
        setQueuedExercises((current) => {
          const next = new Set(current)
          synced.forEach((attempt) => next.delete(attempt.exerciseId))
          rejected.forEach((attempt) => next.delete(attempt.exerciseId))
          return next
        })
      })
    }

    window.addEventListener(ATTEMPT_QUEUE_SYNC_EVENT, handleSync)
    return () => window.removeEventListener(ATTEMPT_QUEUE_SYNC_EVENT, handleSync)
  }, [refetchPracticeSession, session, userId])

  async function begin(
    selectedMode: PracticeMode = mode,
    sourceSessionId?: number,
    selectedFilters: PracticeFilters = filters,
  ) {
    setNavigationError('')
    try {
      const created = await createSession.mutateAsync({
        idempotency_key: crypto.randomUUID(),
        mode: selectedMode,
        ...(selectedFilters.activityType
          ? { activity_type: selectedFilters.activityType }
          : {}),
        ...(selectedFilters.skill ? { skill: selectedFilters.skill } : {}),
        ...(selectedFilters.objective ? { objective: selectedFilters.objective } : {}),
        ...(sourceSessionId ? { source_session_id: sourceSessionId } : {}),
      })
      setSessionId(created.id)
      setResumeAccepted(true)
      setLocalPosition(null)
      setQueuedExercises(new Set())
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
      setQueuedExercises((current) => new Set(current).add(event.exerciseId))
      return
    }

    if (event.type === 'hint') {
      setAnnouncement(`Dica ${event.level} aberta.`)
    }
    await sessionQuery.refetch()
  }

  async function moveTo(position: number) {
    if (!session || !session.items.some((item) => item.position === position)) return
    setNavigationError('')
    setLocalPosition(position)
    writeLocalPosition(userId, session.id, position)
    setAnnouncement(`Questão ${position + 1} de ${session.summary.total}.`)

    if (!online) return
    await reconcilePosition(position, session)
  }

  if (activeQuery.isPending || allExercises.isPending) {
    return <p role="status">Carregando o laboratório de exercícios…</p>
  }

  if (activeQuery.error || allExercises.error) {
    const error = activeQuery.error ?? allExercises.error
    return (
      <div className="practice-state error" role="alert">
        <h2>Não foi possível abrir os exercícios</h2>
        <p>{error?.message}</p>
        <button
          type="button"
          className="btn ghost"
          onClick={() => {
            void activeQuery.refetch()
            void allExercises.refetch()
          }}
        >
          Tentar novamente
        </button>
      </div>
    )
  }

  if (!resumeAccepted && activeSession?.content_changed) {
    const staleFilters = filtersFromSession(activeSession)
    return (
      <div className="practice-state warning" role="status">
        <p className="study-kicker">Conteúdo atualizado</p>
        <h2>Os exercícios mudaram desde o início desta sessão</h2>
        <p>
          Seu histórico anterior continuará registrado. Comece uma sessão nova para não misturar
          versões do conteúdo.
        </p>
        <button
          type="button"
          className="btn"
          disabled={createSession.isPending || !online}
          onClick={() => void begin('guided', undefined, staleFilters)}
        >
          Recomeçar com conteúdo atualizado
        </button>
      </div>
    )
  }

  if (!resumeAccepted && activeSession) {
    return (
      <div className="practice-resume">
        <p className="study-kicker">Sessão em andamento</p>
        <h2>Continue de onde parou</h2>
        <p>
          {PRACTICE_MODE_LABELS[activeSession.mode]} · questão{' '}
          {activeSession.current_position + 1} de {activeSession.summary.total}
        </p>
        <div className="practice-resume-progress">
          <span>{activeSession.summary.completed} concluídas</span>
          <span>{activeSession.summary.pending} pendentes</span>
        </div>
        <button type="button" className="btn" onClick={() => acceptResume(activeSession)}>
          Retomar sessão
        </button>
      </div>
    )
  }

  if (sessionId !== null && (sessionQuery.isPending || !session)) {
    if (sessionQuery.error) {
      return (
        <div className="practice-state error" role="alert">
          <h2>Não foi possível retomar esta sessão</h2>
          <p>{sessionQuery.error.message}</p>
          <button type="button" className="btn ghost" onClick={() => void sessionQuery.refetch()}>
            Tentar novamente
          </button>
        </div>
      )
    }
    return <p role="status">Retomando sua sessão…</p>
  }

  if (session?.content_changed) {
    const staleFilters = filtersFromSession(session)
    return (
      <div className="practice-state warning" role="status">
        <p className="study-kicker">Conteúdo atualizado</p>
        <h2>Esta sessão usa uma versão anterior dos exercícios</h2>
        <p>O histórico foi preservado, mas as respostas novas precisam usar a versão atual.</p>
        <button
          type="button"
          className="btn"
          disabled={createSession.isPending || !online}
          onClick={() => void begin('guided', undefined, staleFilters)}
        >
          Recomeçar com conteúdo atualizado
        </button>
      </div>
    )
  }

  if (session && session.status === 'completed' && showSummary) {
    const fragile = session.summary.corrected + session.summary.revealed
    return (
      <section className="practice-summary" aria-labelledby="practice-summary-title">
        <p className="study-kicker">Sessão concluída</p>
        <h2 id="practice-summary-title">Resumo da sua prática</h2>
        <dl>
          <div>
            <dt>Primeira tentativa</dt>
            <dd>{session.summary.first_try_correct}</dd>
          </div>
          <div>
            <dt>Após correção</dt>
            <dd>{session.summary.corrected}</dd>
          </div>
          <div>
            <dt>Respostas reveladas</dt>
            <dd>{session.summary.revealed}</dd>
          </div>
          <div>
            <dt>Total</dt>
            <dd>{session.summary.total}</dd>
          </div>
        </dl>
        <p className="practice-summary-note">
          Respostas reveladas ajudam a aprender, mas não são contadas como domínio na primeira
          tentativa.
        </p>
        <div className="practice-summary-actions">
          <button
            type="button"
            className="btn"
            disabled={fragile === 0 || createSession.isPending}
            onClick={() => void begin('mistakes', session.id, filtersFromSession(session))}
          >
            Repetir somente erros
          </button>
          <Link className="btn ghost" to="/revisar">
            Ir para revisão
          </Link>
          <Link className="btn ghost" to={studyPath(courseSlug, lessonNumber, 'revisar')}>
            Praticar escrita e fala
          </Link>
        </div>
        {fragile === 0 && <p className="muted">Nenhum item frágil nesta sessão. Muito bem!</p>}
      </section>
    )
  }

  if (!session) {
    const total = allExercises.data?.length ?? 0
    const filteredTotal = filteredExercises.data?.length ?? 0

    if (total === 0) {
      return (
        <div className="practice-state empty">
          <p className="study-kicker">Em preparação</p>
          <h2>Esta aula ainda não possui exercícios</h2>
          <p>Você pode estudar a teoria agora e voltar quando o pack autoral for publicado.</p>
          <Link className="btn ghost" to={lessonPath(courseSlug, lessonNumber)}>
            Voltar à aula
          </Link>
        </div>
      )
    }

    return (
      <section className={`practice-intro ${variant}`} aria-labelledby="practice-intro-title">
        <p className="study-kicker">Laboratório da Aula {lessonNumber}</p>
        <h2 id="practice-intro-title">Escolha como praticar</h2>
        <p className="study-copy">
          Uma questão por vez, com correção explicada. Não há ranking nem tempo obrigatório.
        </p>

        <fieldset className="practice-modes">
          <legend>Modo da sessão</legend>
          {(['guided', 'quick', 'mistakes'] as const).map((itemMode) => (
            <label key={itemMode}>
              <input
                type="radio"
                name={`practice-mode-${lessonNumber}`}
                value={itemMode}
                checked={mode === itemMode}
                disabled={itemMode === 'mistakes'}
                onChange={() => setMode(itemMode)}
              />
              <span>
                <strong>{PRACTICE_MODE_LABELS[itemMode]}</strong>
                <small>{modeDescription(itemMode)}</small>
              </span>
            </label>
          ))}
        </fieldset>

        {!lockFilters && (
          <div className="practice-filters" aria-label="Filtros de exercícios">
            <label>
              Modalidade
              <select
                value={filters.activityType ?? ''}
                onChange={(event) =>
                  setFilters((current) => ({
                    ...current,
                    activityType: (event.target.value || undefined) as
                      | PracticeActivityType
                      | undefined,
                  }))
                }
              >
                <option value="">Todas</option>
                {options.activityTypes.map((value) => (
                  <option value={value} key={value}>
                    {activityLabel(value)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Competência
              <select
                value={filters.skill ?? ''}
                onChange={(event) =>
                  setFilters((current) => ({
                    ...current,
                    skill: (event.target.value || undefined) as PracticeSkill | undefined,
                  }))
                }
              >
                <option value="">Todas</option>
                {options.skills.map((value) => (
                  <option value={value} key={value}>
                    {SKILL_LABELS[value] ?? value}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Objetivo
              <select
                value={filters.objective ?? ''}
                onChange={(event) =>
                  setFilters((current) => ({
                    ...current,
                    objective: (event.target.value || undefined) as
                      | PracticeObjective
                      | undefined,
                  }))
                }
              >
                <option value="">Todos</option>
                {options.objectives.map((value) => (
                  <option value={value} key={value}>
                    {PRACTICE_OBJECTIVE_LABELS[value]}
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}

        <p className="practice-count" role="status" aria-live="polite">
          {filteredExercises.isPending
            ? 'Atualizando o recorte…'
            : `${filteredTotal} de ${total} atividades disponíveis neste recorte.`}
        </p>
        {filteredExercises.error && (
          <p className="erro" role="alert">
            Não foi possível aplicar os filtros. Tente novamente.
          </p>
        )}
        {!filteredExercises.isPending && !filteredExercises.error && filteredTotal === 0 && (
          <p className="practice-filter-empty">
            Nenhuma atividade combina com estes filtros. Escolha outro recorte.
          </p>
        )}
        {!online && (
          <p className="practice-offline-note" role="status">
            Conecte-se para iniciar uma sessão. Tentativas de uma sessão já aberta continuam
            disponíveis offline.
          </p>
        )}
        <button
          type="button"
          className="btn practice-start"
          disabled={
            createSession.isPending ||
            filteredExercises.isPending ||
            filteredTotal === 0 ||
            !online
          }
          onClick={() => void begin()}
        >
          {createSession.isPending ? 'Iniciando…' : `Começar ${PRACTICE_MODE_LABELS[mode]}`}
        </button>
        {createSession.isError && (
          <p className="erro" role="alert">
            {createSession.error.message}
          </p>
        )}
      </section>
    )
  }

  if (!currentItem || currentIndex < 0) {
    return (
      <div className="practice-state error" role="alert">
        <h2>A posição salva não existe neste pack</h2>
        <p>Recarregue a sessão para voltar a uma questão válida.</p>
        <button type="button" className="btn ghost" onClick={() => void sessionQuery.refetch()}>
          Recarregar sessão
        </button>
      </div>
    )
  }

  const confirmedCompleted = session.summary.completed
  const nextItem = session.items[currentIndex + 1]
  const previousItem = session.items[currentIndex - 1]
  // Dicas e tentativas já atualizam o estado do próprio ExerciseCard. Usar
  // esses contadores na key remontava o formulário durante o refetch e podia
  // apagar uma resposta digitada logo após a dica ou "Tentar novamente".
  // A fila offline é externa ao card e ainda exige reidratação ao sincronizar.
  const cardKey = `${currentItem.exercise.id}:${currentQueued ? 'queued' : 'ready'}`

  return (
    <section className={`practice-runner ${variant}`} aria-labelledby="practice-runner-title">
      <div className="practice-runner-head">
        <div>
          <p className="study-kicker">{PRACTICE_MODE_LABELS[session.mode]}</p>
          <h2 id="practice-runner-title">{lessonTitle}</h2>
        </div>
        <span>
          Questão {currentIndex + 1} de {session.summary.total}
        </span>
      </div>

      <div
        className="practice-progress"
        role="progressbar"
        aria-label="Progresso da sessão de exercícios"
        aria-valuemin={0}
        aria-valuemax={session.summary.total}
        aria-valuenow={confirmedCompleted}
        aria-valuetext={`${confirmedCompleted} de ${session.summary.total} atividades concluídas; ${queuedExercises.size} aguardando correção`}
      >
        <span style={{ width: `${(confirmedCompleted / session.summary.total) * 100}%` }} />
      </div>

      <p className="sr-only" aria-live="polite" aria-atomic="true">
        {announcement}
      </p>

      <div className="practice-question">
        <ExerciseCard
          key={cardKey}
          exercicio={currentItem.exercise}
          numero={currentIndex + 1}
          userId={userId}
          practiceSessionId={session.id}
          courseSlug={courseSlug}
          lessonNumber={lessonNumber}
          initialSessionItem={currentItem}
          initialQueued={currentQueued}
          onActivity={(event) => void refreshAfterActivity(event)}
          promptRef={questionRef}
        />
      </div>

      {navigationError && (
        <p className="practice-navigation-error" role="status">
          {navigationError}
        </p>
      )}
      <nav className="practice-navigation" aria-label="Questões da sessão">
        <button
          type="button"
          className="btn ghost"
          disabled={!previousItem || updatePosition.isPending}
          onClick={() => previousItem && void moveTo(previousItem.position)}
        >
          ← Anterior
        </button>
        <span>
          {confirmedCompleted} concluídas
          {queuedExercises.size > 0
            ? ` · ${queuedExercises.size} aguardando correção`
            : ''}
        </span>
        {nextItem ? (
          <button
            type="button"
            className="btn"
            disabled={!currentCompleted || updatePosition.isPending}
            onClick={() => void moveTo(nextItem.position)}
          >
            Próxima →
          </button>
        ) : (
          <button
            type="button"
            className="btn"
            disabled={session.status !== 'completed' || !currentCompleted || currentQueued}
            onClick={() => setShowSummary(true)}
          >
            {currentQueued ? 'Aguardando correção' : 'Ver resumo'}
          </button>
        )}
      </nav>
      {!nextItem && currentQueued && (
        <p className="practice-offline-note" role="status">
          Esta é a última questão. O resumo será fechado quando a tentativa pendente sincronizar.
        </p>
      )}
      <div className="practice-context-links">
        <Link to={lessonPath(courseSlug, lessonNumber)}>Rever teoria</Link>
        <Link to={studyPath(courseSlug, lessonNumber, 'revisar')}>Escrita e speaking</Link>
      </div>
    </section>
  )
}
