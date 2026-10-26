import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  flatItems,
  useWritingFeedbackHistory,
  useWritingHistory,
  type NotebookScope,
} from '../../api/notebook'
import { studyPath } from '../../routing/courseRoutes'
import { WritingFeedbackProvenance } from '../writing/WritingFeedbackProvenance'
import { SHORT_DATE_TIME } from './labels'
import { useAnnouncedPaging } from './paging'

/**
 * Regras das análises já salvas de uma proposta.
 *
 * O histórico mostra a rubrica de cada análise como ela era quando rodou: o
 * resultado do aluno não é recalculado quando a proposta muda.
 */
function WritingFeedbackHistory({
  promptId,
  feedbackCount,
}: {
  promptId: number
  feedbackCount: number
}) {
  const [open, setOpen] = useState(false)
  const query = useWritingFeedbackHistory(promptId, open)
  const items = flatItems(query.data)
  const { statusRef, loadMore } = useAnnouncedPaging(query.fetchNextPage)

  return (
    <details onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>Regras das análises salvas</summary>
      {query.isPending && items.length === 0 && <p>Carregando análises…</p>}
      {query.isError && <p role="alert">Não foi possível carregar as análises salvas.</p>}
      {items.map((feedback) => (
        <div key={feedback.id}>
          <time dateTime={feedback.created_at}>
            {SHORT_DATE_TIME.format(new Date(feedback.created_at))}
          </time>
          <WritingFeedbackProvenance feedback={feedback} />
        </div>
      ))}
      {query.hasNextPage && (
        <button type="button" disabled={query.isFetchingNextPage} onClick={() => void loadMore()}>
          {query.isFetchingNextPage ? 'Carregando mais…' : 'Carregar mais análises'}
        </button>
      )}
      {items.length > 0 && (
        <p ref={statusRef} tabIndex={-1} role="status" className="muted">
          {items.length} de {feedbackCount} análises carregadas.
        </p>
      )}
    </details>
  )
}

/** Produções escritas do recorte, com as versões e análises de cada proposta. */
export function WritingHistorySection({ scope }: { scope: NotebookScope }) {
  const query = useWritingHistory(scope)
  const items = flatItems(query.data)
  const { statusRef, loadMore } = useAnnouncedPaging(query.fetchNextPage)

  return (
    <section aria-labelledby="texts-title">
      <p className="study-kicker">Writing</p>
      <h2 id="texts-title">Textos e correções</h2>
      {query.isPending && <p className="muted">Carregando textos…</p>}
      {query.isError && <p className="erro">Não foi possível carregar os textos.</p>}
      {items.length === 0 && !query.isPending && !query.isError && (
        <p className="notebook-empty">Você ainda não começou uma produção escrita.</p>
      )}
      <ul className="notebook-writing-list">
        {items.map((item) => (
          <li key={item.prompt_id}>
            <div>
              <span>{item.course_title} · Aula {item.lesson_number} · {item.lesson_title}</span>
              <strong>{item.prompt_title}</strong>
              <small>{item.revision_count} versões · {item.feedback_count} análises</small>
              {item.feedback_count > 0 && (
                <WritingFeedbackHistory
                  promptId={item.prompt_id}
                  feedbackCount={item.feedback_count}
                />
              )}
            </div>
            <Link to={studyPath(item.course_slug, item.lesson_number, 'revisar')}>
              Abrir texto
            </Link>
          </li>
        ))}
      </ul>
      {query.hasNextPage && (
        <button
          type="button"
          className="btn ghost"
          disabled={query.isFetchingNextPage}
          onClick={() => void loadMore()}
        >
          {query.isFetchingNextPage ? 'Carregando mais…' : 'Carregar mais textos'}
        </button>
      )}
      {items.length > 0 && (
        <p ref={statusRef} tabIndex={-1} role="status" className="muted">
          {items.length} textos carregados.
        </p>
      )}
    </section>
  )
}
