import type { WritingFeedback } from '../../api/client'
import { WritingFeedbackProvenance } from './WritingFeedbackProvenance'

/** O veredito da rubrica e, quando houver, o comentário automatizado.
 *
 * O rótulo de origem vem primeiro e sempre: o aluno precisa saber se aquilo
 * saiu de regra local ou de modelo antes de ler o conteúdo.
 */
export function WritingFeedbackPanel({
  feedback, onRate,
}: {
  feedback: WritingFeedback
  onRate: (rating: 'helpful' | 'not_helpful') => void
}) {
  return (
    <div className={`writing-feedback ${feedback.ready ? 'ready' : ''}`} aria-live="polite">
      <p className="assist-label">
        {feedback.analysis_mode === 'assisted'
          ? `Automatizado por ${feedback.provider} · somente avaliação`
          : feedback.analysis_mode === 'fallback'
            ? 'Assistência indisponível · rubrica local preservada'
            : 'Análise automática por regras locais'}
      </p>
      <h3>{feedback.ready ? 'Critérios automáticos atendidos' : 'O que revisar agora'}</h3>
      <WritingFeedbackProvenance feedback={feedback} />
      <ul>
        {feedback.checks.map((check) => (
          <li key={check.code} className={check.passed ? 'passed' : ''}>
            <span aria-hidden="true">{check.passed ? '✓' : '○'}</span>
            <span>
              <strong>{check.label}</strong>
              {!check.passed && <small>{check.suggestion}</small>}
            </span>
          </li>
        ))}
      </ul>
      {feedback.assisted_summary && (
        <div className="assist-writing-copy">
          <strong>Comentário experimental</strong>
          <p>{feedback.assisted_summary}</p>
          {feedback.assisted_suggestions.length > 0 && (
            <ul>
              {feedback.assisted_suggestions.map((suggestion, index) => (
                <li key={`${String(suggestion.criterion)}-${index}`}>
                  <strong>{String(suggestion.criterion)}</strong>
                  <span>{String(suggestion.message)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {feedback.low_confidence && (
        <p className="assist-warning" role="alert">
          Baixa confiança: use este comentário como hipótese e confira pela rubrica.
        </p>
      )}
      {feedback.analysis_mode === 'assisted' && (
        <div className="assist-rating" aria-label="Avaliar feedback automático">
          <span>Este comentário ajudou?</span>
          <button type="button" aria-pressed={feedback.human_rating === 'helpful'} onClick={() => onRate('helpful')}>
            Sim
          </button>
          <button type="button" aria-pressed={feedback.human_rating === 'not_helpful'} onClick={() => onRate('not_helpful')}>
            Não
          </button>
        </div>
      )}
    </div>
  )
}
