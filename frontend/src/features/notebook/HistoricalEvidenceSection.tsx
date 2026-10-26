import { flatItems, useHistoricalEvidence } from '../../api/notebook'
import { HistoricalContentDetails } from '../history/HistoricalContentDetails'
import { HISTORY_LABELS, SHORT_DATE_TIME } from './labels'
import { useAnnouncedPaging } from './paging'

/**
 * Conteúdo capturado nas evidências da conta.
 *
 * De propósito sem link para a aula atual e sem os filtros de escopo: o valor
 * desta lista é justamente mostrar o que foi avaliado, mesmo que a aula tenha
 * mudado ou sido arquivada depois.
 */
export function HistoricalEvidenceSection() {
  const query = useHistoricalEvidence()
  const items = flatItems(query.data)
  const { statusRef, loadMore } = useAnnouncedPaging(query.fetchNextPage)

  return (
    <section aria-labelledby="historical-content-title">
      <p className="study-kicker">Memória do conteúdo</p>
      <h2 id="historical-content-title">Conteúdo histórico preservado</h2>
      <p className="muted">
        Evidências capturadas em todos os cursos permanecem consultáveis mesmo se o conteúdo
        atual mudar ou for arquivado. Por isso, esta lista não cria links para a aula atual e
        não é afetada pelos filtros acima.
      </p>
      {query.isPending && items.length === 0 && (
        <p className="muted">Carregando conteúdo histórico…</p>
      )}
      {query.isError && <p className="erro">Não foi possível carregar o conteúdo histórico.</p>}
      {items.length === 0 && !query.isPending && !query.isError && (
        <p className="notebook-empty">Nenhum conteúdo foi capturado nas evidências desta conta.</p>
      )}
      <ul className="notebook-history-list">
        {items.map((item) => (
          <li key={`${item.evidence_kind}:${item.evidence_id}`}>
            <div className="notebook-entry-meta">
              <span>{HISTORY_LABELS[item.evidence_kind]}</span>
              <span>snapshot {item.schema_version}</span>
              <time dateTime={item.captured_at}>
                {SHORT_DATE_TIME.format(new Date(item.captured_at))}
              </time>
            </div>
            <HistoricalContentDetails kind={item.evidence_kind} evidenceId={item.evidence_id} />
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
          {query.isFetchingNextPage ? 'Carregando mais…' : 'Carregar mais conteúdo histórico'}
        </button>
      )}
      {items.length > 0 && (
        <p ref={statusRef} tabIndex={-1} role="status" className="muted">
          {items.length} evidências históricas carregadas.
        </p>
      )}
    </section>
  )
}
