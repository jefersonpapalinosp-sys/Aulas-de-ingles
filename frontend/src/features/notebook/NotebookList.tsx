import { useState } from 'react'
import type { LessonSummary, NotebookEntry, NotebookKind } from '../../api/client'
import {
  flatItems,
  useDeleteNotebookEntry,
  useNotebookEntries,
  useUpdateNotebookEntry,
  type NotebookScope,
} from '../../api/notebook'
import { KINDS, SHORT_DATE_TIME, failureMessage, kindLabel } from './labels'

type Props = {
  scope: NotebookScope
  lessons: LessonSummary[]
  onMessage: (message: string) => void
}

/** Lista filtrável das anotações, com edição no lugar e páginas acumuladas. */
export function NotebookList({ scope, lessons, onMessage }: Props) {
  const [lessonFilter, setLessonFilter] = useState<'all' | number>('all')
  const [kindFilter, setKindFilter] = useState<'all' | NotebookKind>('all')
  const [editing, setEditing] = useState<NotebookEntry | null>(null)
  const entries = useNotebookEntries(scope, {
    lesson: lessonFilter === 'all' ? undefined : lessonFilter,
    kind: kindFilter === 'all' ? undefined : kindFilter,
  })
  const update = useUpdateNotebookEntry()
  const remove = useDeleteNotebookEntry()
  const items = flatItems(entries.data)

  async function saveEdit() {
    if (!editing || !editing.content.trim()) return
    onMessage('')
    try {
      await update.mutateAsync(editing)
      setEditing(null)
      onMessage('Anotação atualizada.')
    } catch (error) {
      onMessage(failureMessage(error, 'Não foi possível atualizar a anotação.'))
    }
  }

  async function removeEntry(entryId: number) {
    onMessage('')
    try {
      await remove.mutateAsync(entryId)
      if (editing?.id === entryId) setEditing(null)
      onMessage('Anotação excluída.')
    } catch (error) {
      onMessage(failureMessage(error, 'Não foi possível excluir a anotação.'))
    }
  }

  return (
    <section aria-labelledby="notes-title">
      <div className="notebook-section-head">
        <div>
          <p className="study-kicker">Memória pessoal</p>
          <h2 id="notes-title">Minhas anotações</h2>
        </div>
        <div className="notebook-filters">
          <label>
            Aula
            <select
              value={lessonFilter}
              onChange={(event) =>
                setLessonFilter(event.target.value === 'all' ? 'all' : Number(event.target.value))
              }
            >
              <option value="all">Todas</option>
              {lessons.map((lesson) => (
                <option key={`${lesson.course_slug}:${lesson.number}`} value={lesson.number}>
                  {lesson.number}
                </option>
              ))}
            </select>
          </label>
          <label>
            Tipo
            <select
              value={kindFilter}
              onChange={(event) => setKindFilter(event.target.value as 'all' | NotebookKind)}
            >
              <option value="all">Todos</option>
              {KINDS.map((item) => (
                <option key={item.value} value={item.value}>{item.label}</option>
              ))}
            </select>
          </label>
        </div>
      </div>
      {entries.isPending && <p className="muted">Carregando caderno…</p>}
      {entries.isError && <p className="erro">Não foi possível carregar o caderno.</p>}
      {!entries.isPending && items.length === 0 && (
        <p className="notebook-empty">Nenhuma anotação com estes filtros.</p>
      )}
      <ul className="notebook-list">
        {items.map((entry) => (
          <li key={entry.id}>
            {editing?.id === entry.id ? (
              <div className="notebook-edit">
                <select
                  aria-label="Tipo da anotação"
                  value={editing.kind}
                  onChange={(event) =>
                    setEditing({ ...editing, kind: event.target.value as NotebookKind })
                  }
                >
                  {KINDS.map((item) => (
                    <option key={item.value} value={item.value}>{item.label}</option>
                  ))}
                </select>
                <textarea
                  aria-label="Conteúdo da anotação"
                  maxLength={2000}
                  value={editing.content}
                  onChange={(event) => setEditing({ ...editing, content: event.target.value })}
                />
                <div>
                  <button type="button" onClick={() => void saveEdit()}>Salvar alteração</button>
                  <button type="button" onClick={() => setEditing(null)}>Cancelar</button>
                </div>
              </div>
            ) : (
              <>
                <div className="notebook-entry-meta">
                  <span>{kindLabel(entry.kind)}</span>
                  <span>{entry.course_title} · Aula {entry.lesson_number}</span>
                  <time dateTime={entry.updated_at}>
                    {SHORT_DATE_TIME.format(new Date(entry.updated_at))}
                  </time>
                </div>
                <p>{entry.content}</p>
                <div className="notebook-entry-actions">
                  <button type="button" onClick={() => setEditing(entry)}>Editar</button>
                  <button type="button" onClick={() => void removeEntry(entry.id)}>Excluir</button>
                </div>
              </>
            )}
          </li>
        ))}
      </ul>
      {entries.hasNextPage && (
        <button
          type="button"
          className="btn ghost"
          disabled={entries.isFetchingNextPage}
          onClick={() => void entries.fetchNextPage()}
        >
          {entries.isFetchingNextPage ? 'Carregando mais…' : 'Carregar mais anotações'}
        </button>
      )}
    </section>
  )
}
