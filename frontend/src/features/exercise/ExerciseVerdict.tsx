import type { AttemptFeedback, Exercise } from '../../api/client'
import { Markdown } from '../../components/Markdown'
import { classificationEntries } from './classification'

export type Veredito =
  | { tipo: 'nada' }
  | { tipo: 'certo'; explicacao: string | null }
  | { tipo: 'errado'; feedback: AttemptFeedback }
  | { tipo: 'revelado'; respostas: string[]; explicacao: string }
  | { tipo: 'fila' }
  | { tipo: 'falhou'; mensagem: string }

/** O veredito da tentativa.
 *
 * "Ainda não" e "Erro" usam `role="alert"`: eles exigem ação do aluno — tentar
 * de novo, ou conferir o que falhou — e um leitor de tela precisa anunciá-los
 * na hora, não quando sobrar silêncio. Acerto, gabarito e fila seguem
 * `role="status"`, que é o anúncio educado.
 */
export function ExerciseVerdict({
  veredito, exercicio, onRetry,
}: {
  veredito: Veredito
  exercicio: Exercise
  onRetry: () => void
}) {
  if (veredito.tipo === 'nada') return null
  const urgente = veredito.tipo === 'errado' || veredito.tipo === 'falhou'
  return (
    <div className={`fb ${veredito.tipo}`} role={urgente ? 'alert' : 'status'}>
      {veredito.tipo === 'certo' && (
        <>
          <span className="tag">Correto</span>
          {veredito.explicacao && (
            <span className="why"><Markdown>{veredito.explicacao}</Markdown></span>
          )}
        </>
      )}
      {veredito.tipo === 'errado' && (
        <>
          <span className="tag">Ainda não</span>
          <span className="answer-diff" aria-label="Trechos da sua resposta">
            {veredito.feedback.tokens.map((token, index) => (
              <mark className={token.status} key={`${token.text}-${index}`}>{token.text}</mark>
            ))}
          </span>
          <span className="why">{veredito.feedback.message}</span>
          <button type="button" className="feedback-retry" onClick={onRetry}>
            Tentar novamente
          </button>
        </>
      )}
      {veredito.tipo === 'revelado' && (
        <>
          <span className="tag">Resposta</span>
          {exercicio.activity_type === 'classification' ? (
            <div className="classification-solutions">
              {veredito.respostas.map((answer, answerIndex) => {
                const entries = classificationEntries(answer)
                return entries ? (
                  <dl key={answer} aria-label={`Gabarito ${answerIndex + 1}`}>
                    {entries.map(([item, category]) => (
                      <div key={item}>
                        <dt>{item}</dt>
                        <dd>{category}</dd>
                      </div>
                    ))}
                  </dl>
                ) : (
                  <strong className="gabarito" key={answer}>{answer}</strong>
                )
              })}
            </div>
          ) : (
            <strong className="gabarito">{veredito.respostas.join('  ·  ')}</strong>
          )}
          <span className="why"><Markdown>{veredito.explicacao}</Markdown></span>
        </>
      )}
      {veredito.tipo === 'falhou' && (
        <>
          <span className="tag">Erro</span>
          <span className="why">{veredito.mensagem}</span>
        </>
      )}
      {veredito.tipo === 'fila' && (
        <>
          <span className="tag">Na fila</span>
          <span className="why">
            Sua tentativa foi salva neste dispositivo e será corrigida quando a conexão voltar.
          </span>
        </>
      )}
    </div>
  )
}
