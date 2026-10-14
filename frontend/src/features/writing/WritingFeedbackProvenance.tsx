import type { WritingFeedback } from '../../api/client'

export function WritingFeedbackProvenance({ feedback }: { feedback: WritingFeedback }) {
  const legacy = !feedback.algorithm_version || feedback.algorithm_version === 'legacy-v1'
  return (
    <div className="writing-feedback-provenance">
      <p className="assist-label">
        {legacy ? 'Regra anterior · resultado preservado' : `Regra ${feedback.algorithm_version}`}
        {feedback.rubric_version && (
          <span title={feedback.rubric_version}> · rubrica {feedback.rubric_version.slice(7, 19)}</span>
        )}
      </p>
      {legacy && (
        <p className="muted">
          Esta análise é anterior à revisão das rubricas. Expressões e quantidades podiam ser
          avaliadas incorretamente. O resultado original não foi recalculado; uma nova análise
          usará a regra atual.
        </p>
      )}
      <p className="muted">
        {feedback.evaluation_scope || 'A verificação automática não garante gramática correta, coerência ou atendimento completo à proposta.'}
      </p>
    </div>
  )
}
