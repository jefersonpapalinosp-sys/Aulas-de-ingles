import type { ReviewItem } from '../../api/client'
import { Markdown } from '../../components/Markdown'
import { NOTES, TYPE_LABELS, durationLabel } from './reviewLabels'

/** A carta de revisão: pergunta, resposta e as quatro notas.
 *
 * A resposta só aparece depois de o aluno pedir. Mostrar as duas faces de uma
 * vez transformaria recuperação ativa em leitura, que é o que a revisão
 * espaçada existe para evitar.
 */
export function ReviewCard({
  item, flipped, grading, blocked, suspending, removing, onFlip, onAnswer, onSuspend, onRemove,
}: {
  item: ReviewItem
  flipped: boolean
  grading: boolean
  blocked: boolean
  suspending: boolean
  removing: boolean
  onFlip: () => void
  onAnswer: (quality: number) => void
  onSuspend: () => void
  onRemove: () => void
}) {
  return (
    <>
      <div className="review-card-meta">
        <span>{TYPE_LABELS[item.item_type]}</span>
        <span>{item.skill}</span>
        <span>{durationLabel(item.estimated_seconds)}</span>
        <span>{item.course_title} · Aula {item.lesson_number}</span>
      </div>
      <aside className="review-reason">
        <strong>Por que voltou?</strong>
        <span>{item.reason}</span>
      </aside>

      <div className={`carta review-${item.item_type}`}>
        <p className="carta-origem">
          {item.course_title} · Aula {item.lesson_number} · {TYPE_LABELS[item.item_type]}
        </p>
        <div className="carta-termo"><Markdown>{item.prompt}</Markdown></div>
        {item.prompt_note && <p className="carta-ipa">{item.prompt_note}</p>}
        {item.media_url && (
          <audio className="review-audio" controls preload="metadata" src={item.media_url}>
            Seu navegador não suporta áudio.
          </audio>
        )}

        {flipped ? (
          <div className="carta-verso">
            <div className="carta-traducao"><Markdown>{item.answer}</Markdown></div>
            {item.context && <div className="carta-exemplo"><Markdown>{item.context}</Markdown></div>}
          </div>
        ) : (
          <button className="btn virar" onClick={onFlip}>Mostrar resposta</button>
        )}
      </div>

      {flipped && (
        <div className="notas">
          {NOTES.map((note) => (
            <button
              key={note.quality}
              className={`nota ${note.className}`}
              onClick={() => onAnswer(note.quality)}
              disabled={grading || blocked}
            >
              <span className="nota-rotulo">{note.label}</span>
              <span className="nota-tecla">{note.key}</span>
            </button>
          ))}
        </div>
      )}

      <div className="review-item-actions">
        <span>
          {flipped ? '1–4 para avaliar' : 'espaço ou enter para revelar'} ·{' '}
          {item.repetitions === 0
            ? 'primeira vez'
            : `${item.repetitions} acertos, ${item.lapses} tropeços`}
        </span>
        <button type="button" onClick={onSuspend} disabled={suspending || blocked}>
          Suspender item
        </button>
        <button type="button" onClick={onRemove} disabled={removing || blocked}>
          Excluir item
        </button>
      </div>
    </>
  )
}
