import type { ReviewItem } from '../../api/client'
import { TYPE_LABELS } from './reviewLabels'

/** Itens que o aluno pausou.
 *
 * A seção aparece também quando a leitura falha: dizer que a lista não carregou
 * é diferente de dizer que não há nada pausado.
 */
export function SuspendedItems({
  items, failed, fetching, nextCursor, statusRef, onReactivate, onRemove, onLoadMore,
}: {
  items: ReviewItem[]
  failed: boolean
  fetching: boolean
  nextCursor?: string
  statusRef: React.Ref<HTMLParagraphElement>
  onReactivate: (itemId: number) => void
  onRemove: (itemId: number) => void
  onLoadMore: (cursor: string) => void
}) {
  if (!failed && items.length === 0) return null
  return (
    <section className="review-suspended">
      <div className="sec-h">
        <span className="num">PAUSA</span>
        <h2>Itens suspensos</h2>
      </div>
      {failed && <p role="alert">Falha ao carregar.</p>}
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            <div>
              <span>
                {item.course_title} · Aula {item.lesson_number} · {TYPE_LABELS[item.item_type]}
              </span>
              <strong>{item.prompt}</strong>
            </div>
            <button type="button" onClick={() => onReactivate(item.id)}>Reativar</button>
            <button type="button" onClick={() => onRemove(item.id)}>Excluir</button>
          </li>
        ))}
      </ul>
      {nextCursor && (
        <button
          type="button"
          className="btn ghost"
          disabled={fetching}
          onClick={() => onLoadMore(nextCursor)}
        >
          {fetching ? 'Carregando mais…' : 'Carregar mais'}
        </button>
      )}
      {items.length > 0 && (
        <p ref={statusRef} tabIndex={-1} role="status">
          {items.length} suspensos carregados.
        </p>
      )}
    </section>
  )
}
