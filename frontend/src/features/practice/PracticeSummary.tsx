import { Link } from 'react-router-dom'
import { studyPath } from '../../routing/courseRoutes'
import type { PracticeSession } from './types'

/** Fechamento da sessão.
 *
 * Resposta revelada aparece separada de acerto na primeira tentativa de
 * propósito: as duas ajudam a aprender, mas só uma delas é domínio.
 */
export function PracticeSummary({
  session, courseSlug, lessonNumber, starting, onRepeatMistakes,
}: {
  session: PracticeSession
  courseSlug: string
  lessonNumber: number
  starting: boolean
  onRepeatMistakes: () => void
}) {
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
        <button type="button" className="btn" disabled={fragile === 0 || starting} onClick={onRepeatMistakes}>
          Repetir somente erros
        </button>
        <Link className="btn ghost" to="/revisar">Ir para revisão</Link>
        <Link className="btn ghost" to={studyPath(courseSlug, lessonNumber, 'revisar')}>
          Praticar escrita e fala
        </Link>
      </div>
      {fragile === 0 && <p className="muted">Nenhum item frágil nesta sessão. Muito bem!</p>}
    </section>
  )
}
