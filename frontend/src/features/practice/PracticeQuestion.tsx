import { Link } from 'react-router-dom'
import { ExerciseCard } from '../../components/ExerciseCard'
import { lessonPath, studyPath } from '../../routing/courseRoutes'
import { PRACTICE_MODE_LABELS, type ExerciseActivityEvent, type PracticeSession } from './types'

/** A questão corrente e a navegação da sessão.
 *
 * "Próxima" só libera depois que o item corrente foi concluído — inclusive
 * quando a conclusão está na fila offline, caso em que o rótulo passa a ser
 * "Aguardando correção": avançar ali esconderia do aluno que falta confirmar.
 */
export function PracticeQuestion({
  session, index, item, lessonTitle, courseSlug, lessonNumber, userId, variant,
  queued, queuedCount, completed, announcement, storageWarning, navigationError,
  navigating, questionRef, onMove, onSummary, onActivity,
}: {
  session: PracticeSession
  index: number
  item: PracticeSession['items'][number]
  lessonTitle: string
  courseSlug: string
  lessonNumber: number
  userId: number
  variant: 'full' | 'embedded'
  queued: boolean
  queuedCount: number
  completed: boolean
  announcement: string
  storageWarning: string
  navigationError: string
  navigating: boolean
  questionRef: React.RefObject<HTMLHeadingElement | null>
  onMove: (position: number) => void
  onSummary: () => void
  onActivity: (event: ExerciseActivityEvent) => void
}) {
  const confirmedCompleted = session.summary.completed
  const nextItem = session.items[index + 1]
  const previousItem = session.items[index - 1]
  // Dicas e tentativas já atualizam o estado do próprio ExerciseCard. Usar
  // esses contadores na key remontava o formulário durante o refetch e podia
  // apagar uma resposta digitada logo após a dica ou "Tentar novamente".
  // A fila offline é externa ao card e ainda exige reidratação ao sincronizar.
  const cardKey = `${item.exercise.id}:${queued ? 'queued' : 'ready'}`

  return (
    <section className={`practice-runner ${variant}`} aria-labelledby="practice-runner-title">
      <div className="practice-runner-head">
        <div>
          <p className="study-kicker">{PRACTICE_MODE_LABELS[session.mode]}</p>
          <h2 id="practice-runner-title">{lessonTitle}</h2>
        </div>
        <span>Questão {index + 1} de {session.summary.total}</span>
      </div>
      <p className="practice-time-budget">
        Referência de ritmo: cerca de 2 min por item · orçamento sugerido desta sessão:{' '}
        {session.summary.total * 2} min. Não há cronômetro nem penalidade por levar mais tempo.
      </p>

      <div
        className="practice-progress"
        role="progressbar"
        aria-label="Progresso da sessão de exercícios"
        aria-valuemin={0}
        aria-valuemax={session.summary.total}
        aria-valuenow={confirmedCompleted}
        aria-valuetext={`${confirmedCompleted} de ${session.summary.total} atividades concluídas; ${queuedCount} aguardando correção`}
      >
        <span style={{ width: `${(confirmedCompleted / session.summary.total) * 100}%` }} />
      </div>

      <p className="sr-only" aria-live="polite" aria-atomic="true">{announcement}</p>

      <div className="practice-question">
        <ExerciseCard
          key={cardKey}
          exercicio={item.exercise}
          numero={index + 1}
          userId={userId}
          practiceSessionId={session.id}
          courseSlug={courseSlug}
          lessonNumber={lessonNumber}
          initialSessionItem={item}
          initialQueued={queued}
          onActivity={onActivity}
          promptRef={questionRef}
        />
      </div>

      {storageWarning && <p role="alert" className="erro">{storageWarning}</p>}
      {navigationError && <p className="practice-navigation-error" role="status">{navigationError}</p>}
      <nav className="practice-navigation" aria-label="Questões da sessão">
        <button
          type="button"
          className="btn ghost"
          disabled={!previousItem || navigating}
          onClick={() => previousItem && onMove(previousItem.position)}
        >
          ← Anterior
        </button>
        <span>
          {confirmedCompleted} concluídas
          {queuedCount > 0 ? ` · ${queuedCount} aguardando correção` : ''}
        </span>
        {nextItem ? (
          <button
            type="button"
            className="btn"
            disabled={!completed || navigating}
            onClick={() => onMove(nextItem.position)}
          >
            Próxima →
          </button>
        ) : (
          <button
            type="button"
            className="btn"
            disabled={session.status !== 'completed' || !completed || queued}
            onClick={onSummary}
          >
            {queued ? 'Aguardando correção' : 'Ver resumo'}
          </button>
        )}
      </nav>
      {!nextItem && queued && (
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
