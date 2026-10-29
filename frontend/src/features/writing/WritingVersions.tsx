import type { WritingRevision } from '../../api/client'
import { wordDiff } from './wordDiff'

/** Histórico de versões: restaurar no editor ou comparar com o texto atual. */
export function WritingVersions({
  revisions, loading, failed, fetching, nextCursor, statusRef, onRestore, onCompare, onLoadMore,
}: {
  revisions: WritingRevision[]
  loading: boolean
  failed: boolean
  fetching: boolean
  nextCursor?: string
  statusRef: React.Ref<HTMLParagraphElement>
  onRestore: (text: string) => void
  onCompare: (revision: WritingRevision) => void
  onLoadMore: (cursor: string) => void
}) {
  if (revisions.length === 0) {
    if (loading) return <p>Carregando versões…</p>
    if (failed) return <p role="alert">Não foi possível carregar as versões salvas.</p>
    return null
  }
  return (
    <div className="writing-history">
      <h3>Versões salvas</h3>
      <ul>
        {revisions.map((revision) => (
          <li key={revision.id}>
            <span>Versão {revision.version}</span>
            <time dateTime={revision.created_at}>
              {new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(revision.created_at))}
            </time>
            <button type="button" onClick={() => onRestore(revision.text)}>Restaurar no editor</button>
            <button type="button" onClick={() => onCompare(revision)}>Comparar com texto atual</button>
          </li>
        ))}
      </ul>
      {nextCursor && (
        <button type="button" disabled={fetching} onClick={() => onLoadMore(nextCursor)}>
          {fetching ? 'Carregando mais…' : 'Carregar mais versões'}
        </button>
      )}
      <p ref={statusRef} tabIndex={-1} role="status">
        {revisions.length} {revisions.length === 1 ? 'versão carregada' : 'versões carregadas'}.
      </p>
    </div>
  )
}

/** Comparação palavra a palavra entre uma versão salva e o texto do editor. */
export function WritingDiff({
  comparison, text, onClose,
}: {
  comparison: WritingRevision
  text: string
  onClose: () => void
}) {
  return (
    <div className="writing-diff" aria-live="polite">
      <div className="writing-diff-head">
        <div>
          <p className="study-kicker">Comparação</p>
          <h3>Versão {comparison.version} → texto atual</h3>
        </div>
        <button type="button" onClick={onClose}>Fechar comparação</button>
      </div>
      <p className="writing-diff-legend">
        <span className="removed">Removido</span>
        <span className="added">Adicionado</span>
      </p>
      <p className="writing-diff-copy" lang="en">
        {wordDiff(comparison.text, text).map((part, index) =>
          part.kind === 'removed' ? (
            <del key={`${index}-${part.text}`}>{part.text}</del>
          ) : part.kind === 'added' ? (
            <ins key={`${index}-${part.text}`}>{part.text}</ins>
          ) : (
            <span key={`${index}-${part.text}`}>{part.text}</span>
          ),
        )}
      </p>
    </div>
  )
}
