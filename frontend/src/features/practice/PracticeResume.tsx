import { PRACTICE_MODE_LABELS, type PracticeSession } from './types'

/** Sessão aberta: retomar é escolha do aluno, não automática.
 *
 * Retomar sozinho roubaria o contexto de quem voltou para começar outra coisa.
 */
export function PracticeResume({
  session, onResume,
}: {
  session: PracticeSession
  onResume: () => void
}) {
  return (
    <div className="practice-resume">
      <p className="study-kicker">Sessão em andamento</p>
      <h2>Continue de onde parou</h2>
      <p>
        {PRACTICE_MODE_LABELS[session.mode]} · questão{' '}
        {session.current_position + 1} de {session.summary.total}
      </p>
      <div className="practice-resume-progress">
        <span>{session.summary.completed} concluídas</span>
        <span>{session.summary.pending} pendentes</span>
      </div>
      <button type="button" className="btn" onClick={onResume}>
        Retomar sessão
      </button>
    </div>
  )
}

/** O pack mudou debaixo da sessão.
 *
 * O histórico anterior fica registrado; o que não pode é resposta nova entrar
 * misturando versões do conteúdo. Então a única saída oferecida é recomeçar.
 */
export function PracticeContentChanged({
  title, note, disabled, onRestart,
}: {
  title: string
  note: string
  disabled: boolean
  onRestart: () => void
}) {
  return (
    <div className="practice-state warning" role="status">
      <p className="study-kicker">Conteúdo atualizado</p>
      <h2>{title}</h2>
      <p>{note}</p>
      <button type="button" className="btn" disabled={disabled} onClick={onRestart}>
        Recomeçar com conteúdo atualizado
      </button>
    </div>
  )
}

/** Falha de leitura com a ação que resolve, nunca um beco sem saída. */
export function PracticeFailure({
  title, message, action, onRetry,
}: {
  title: string
  message?: string
  action: string
  onRetry: () => void
}) {
  return (
    <div className="practice-state error" role="alert">
      <h2>{title}</h2>
      <p>{message}</p>
      <button type="button" className="btn ghost" onClick={onRetry}>{action}</button>
    </div>
  )
}
