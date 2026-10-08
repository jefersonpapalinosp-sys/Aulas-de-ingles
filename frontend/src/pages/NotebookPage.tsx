import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  api,
  authenticatedFetch,
  type NotebookEntry,
  type NotebookKind,
} from '../api/client'
import { useLessons } from '../api/queries'
import { DEFAULT_COURSE_SLUG, studyPath } from '../routing/courseRoutes'

const KINDS: readonly { value: NotebookKind; label: string }[] = [
  { value: 'note', label: 'Anotação livre' },
  { value: 'favorite_phrase', label: 'Frase favorita' },
  { value: 'personal_example', label: 'Exemplo pessoal' },
  { value: 'recurring_error', label: 'Erro recorrente' },
  { value: 'teacher_question', label: 'Pergunta ao professor' },
]

function kindLabel(kind: NotebookKind): string {
  return KINDS.find((item) => item.value === kind)?.label ?? kind
}

export function NotebookPage() {
  const queryClient = useQueryClient()
  const { data: lessons = [] } = useLessons()
  const [lessonFilter, setLessonFilter] = useState<'all' | number>('all')
  const [kindFilter, setKindFilter] = useState<'all' | NotebookKind>('all')
  const [lessonNumber, setLessonNumber] = useState(0)
  const [kind, setKind] = useState<NotebookKind>('note')
  const [content, setContent] = useState('')
  const [editing, setEditing] = useState<NotebookEntry | null>(null)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [exporting, setExporting] = useState(false)
  const [recordingUrl, setRecordingUrl] = useState<string | null>(null)
  const [playingAttemptId, setPlayingAttemptId] = useState<number | null>(null)

  const entriesQuery = useQuery({
    queryKey: ['notebook', lessonFilter, kindFilter],
    queryFn: async () => {
      const { data } = await api.GET('/api/me/notebook', {
        params: {
          query: {
            lesson: lessonFilter === 'all' ? undefined : lessonFilter,
            kind: kindFilter === 'all' ? undefined : kindFilter,
          },
        },
      })
      if (!data) throw new Error('Não foi possível carregar o caderno.')
      return data
    },
    retry: false,
  })
  const writingQuery = useQuery({
    queryKey: ['writing-history'],
    queryFn: async () => {
      const { data } = await api.GET('/api/writing/history')
      if (!data) throw new Error('Não foi possível carregar os textos.')
      return data
    },
    retry: false,
  })
  const speakingQuery = useQuery({
    queryKey: ['speaking-attempts'],
    queryFn: async () => {
      const { data } = await api.GET('/api/speaking/attempts')
      if (!data) throw new Error('Não foi possível carregar as gravações.')
      return data
    },
    retry: false,
  })

  useEffect(
    () => () => {
      if (recordingUrl) URL.revokeObjectURL(recordingUrl)
    },
    [recordingUrl],
  )

  useEffect(() => {
    if (lessonNumber === 0 && lessons[0]) setLessonNumber(lessons[0].number)
  }, [lessonNumber, lessons])

  async function refreshNotebook() {
    await queryClient.invalidateQueries({ queryKey: ['notebook'] })
  }

  async function createEntry() {
    if (!content.trim() || lessonNumber === 0) return
    setSaving(true)
    setMessage('')
    try {
      const { data } = await api.POST('/api/me/notebook', {
        body: { lesson_number: lessonNumber, kind, content },
      })
      if (!data) throw new Error('Falha ao criar anotação.')
      setContent('')
      setMessage('Anotação salva no seu caderno.')
      await refreshNotebook()
    } catch {
      setMessage('Não foi possível salvar a anotação.')
    } finally {
      setSaving(false)
    }
  }

  async function updateEntry() {
    if (!editing || !editing.content.trim()) return
    setSaving(true)
    setMessage('')
    try {
      const { data } = await api.PUT('/api/me/notebook/{entry_id}', {
        params: { path: { entry_id: editing.id } },
        body: { kind: editing.kind, content: editing.content },
      })
      if (!data) throw new Error('Falha ao atualizar anotação.')
      setEditing(null)
      setMessage('Anotação atualizada.')
      await refreshNotebook()
    } catch {
      setMessage('Não foi possível atualizar a anotação.')
    } finally {
      setSaving(false)
    }
  }

  async function deleteEntry(entryId: number) {
    const { response } = await api.DELETE('/api/me/notebook/{entry_id}', {
      params: { path: { entry_id: entryId } },
    })
    if (!response.ok) {
      setMessage('Não foi possível excluir a anotação.')
      return
    }
    if (editing?.id === entryId) setEditing(null)
    setMessage('Anotação excluída.')
    await refreshNotebook()
  }

  async function exportData() {
    setExporting(true)
    setMessage('')
    try {
      const response = await authenticatedFetch('/api/me/export')
      if (!response.ok) throw new Error('Falha na exportação.')
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = url
      link.download = 'aulas-ingles-dados.json'
      link.click()
      URL.revokeObjectURL(url)
      setMessage('Exportação preparada. Confira os downloads do navegador.')
    } catch {
      setMessage('Não foi possível exportar seus dados agora.')
    } finally {
      setExporting(false)
    }
  }

  async function playRecording(attemptId: number) {
    setMessage('Carregando gravação…')
    try {
      const response = await authenticatedFetch(`/api/speaking/attempts/${attemptId}/audio`)
      if (!response.ok) throw new Error('Falha ao carregar a gravação.')
      setRecordingUrl(URL.createObjectURL(await response.blob()))
      setPlayingAttemptId(attemptId)
      setMessage('Gravação carregada.')
    } catch {
      setMessage('Não foi possível carregar essa gravação.')
    }
  }

  async function deleteRecording(attemptId: number) {
    const { response } = await api.DELETE('/api/speaking/attempts/{attempt_id}', {
      params: { path: { attempt_id: attemptId } },
    })
    if (!response.ok) {
      setMessage('Não foi possível excluir essa gravação.')
      return
    }
    if (playingAttemptId === attemptId) {
      setRecordingUrl(null)
      setPlayingAttemptId(null)
    }
    setMessage('Gravação excluída da sua conta.')
    await queryClient.invalidateQueries({ queryKey: ['speaking-attempts'] })
  }

  return (
    <div className="notebook-page">
      <header className="notebook-header">
        <div>
          <p className="eyebrow">Seu espaço privado</p>
          <h1>Caderno de inglês</h1>
          <p className="lead">
            Guarde frases, exemplos, dúvidas e erros que merecem uma nova tentativa.
          </p>
        </div>
        <button type="button" className="btn ghost" disabled={exporting} onClick={() => void exportData()}>
          {exporting ? 'Exportando…' : 'Exportar meus dados'}
        </button>
      </header>
      <p className="notebook-privacy">
        Estas anotações pertencem somente à sua conta. Elas não alteram as aulas e não aparecem
        para outros estudantes.
      </p>
      {message && <p className="notebook-message" role="status">{message}</p>}

      <section className="notebook-compose" aria-labelledby="new-note-title">
        <p className="study-kicker">Nova entrada</p>
        <h2 id="new-note-title">O que você quer lembrar?</h2>
        <div className="notebook-fields">
          <label>
            Aula
            <select value={lessonNumber} onChange={(event) => setLessonNumber(Number(event.target.value))}>
              {lessons.map((lesson) => (
                <option key={lesson.number} value={lesson.number}>Aula {lesson.number} · {lesson.title}</option>
              ))}
            </select>
          </label>
          <label>
            Tipo
            <select value={kind} onChange={(event) => setKind(event.target.value as NotebookKind)}>
              {KINDS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
          </label>
        </div>
        <label className="notebook-editor">
          Conteúdo
          <textarea
            value={content}
            maxLength={2000}
            placeholder="Escreva uma frase, dúvida ou observação…"
            onChange={(event) => setContent(event.target.value)}
          />
        </label>
        <div className="notebook-compose-actions">
          <span>{content.length}/2000</span>
          <button type="button" className="btn" disabled={saving || !content.trim()} onClick={() => void createEntry()}>
            {saving ? 'Salvando…' : 'Salvar no caderno'}
          </button>
        </div>
      </section>

      <section aria-labelledby="notes-title">
        <div className="notebook-section-head">
          <div>
            <p className="study-kicker">Memória pessoal</p>
            <h2 id="notes-title">Minhas anotações</h2>
          </div>
          <div className="notebook-filters">
            <label>
              Aula
              <select value={lessonFilter} onChange={(event) => setLessonFilter(event.target.value === 'all' ? 'all' : Number(event.target.value))}>
                <option value="all">Todas</option>
                {lessons.map((lesson) => <option key={lesson.number} value={lesson.number}>{lesson.number}</option>)}
              </select>
            </label>
            <label>
              Tipo
              <select value={kindFilter} onChange={(event) => setKindFilter(event.target.value as 'all' | NotebookKind)}>
                <option value="all">Todos</option>
                {KINDS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
            </label>
          </div>
        </div>
        {entriesQuery.isPending && <p className="muted">Carregando caderno…</p>}
        {entriesQuery.isError && <p className="erro">Não foi possível carregar o caderno.</p>}
        {entriesQuery.data?.length === 0 && <p className="notebook-empty">Nenhuma anotação com estes filtros.</p>}
        <ul className="notebook-list">
          {entriesQuery.data?.map((entry) => (
            <li key={entry.id}>
              {editing?.id === entry.id ? (
                <div className="notebook-edit">
                  <select
                    aria-label="Tipo da anotação"
                    value={editing.kind}
                    onChange={(event) => setEditing({ ...editing, kind: event.target.value as NotebookKind })}
                  >
                    {KINDS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                  </select>
                  <textarea
                    aria-label="Conteúdo da anotação"
                    maxLength={2000}
                    value={editing.content}
                    onChange={(event) => setEditing({ ...editing, content: event.target.value })}
                  />
                  <div>
                    <button type="button" onClick={() => void updateEntry()}>Salvar alteração</button>
                    <button type="button" onClick={() => setEditing(null)}>Cancelar</button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="notebook-entry-meta">
                    <span>{kindLabel(entry.kind)}</span>
                    <span>Aula {entry.lesson_number}</span>
                    <time dateTime={entry.updated_at}>{new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(entry.updated_at))}</time>
                  </div>
                  <p>{entry.content}</p>
                  <div className="notebook-entry-actions">
                    <button type="button" onClick={() => setEditing(entry)}>Editar</button>
                    <button type="button" onClick={() => void deleteEntry(entry.id)}>Excluir</button>
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="texts-title">
        <p className="study-kicker">Writing</p>
        <h2 id="texts-title">Textos e correções</h2>
        {writingQuery.isPending && <p className="muted">Carregando textos…</p>}
        {writingQuery.isError && <p className="erro">Não foi possível carregar os textos.</p>}
        {writingQuery.data?.length === 0 && <p className="notebook-empty">Você ainda não começou uma produção escrita.</p>}
        <ul className="notebook-writing-list">
          {writingQuery.data?.map((item) => (
            <li key={item.prompt_id}>
              <div>
                <span>Aula {item.lesson_number} · {item.lesson_title}</span>
                <strong>{item.prompt_title}</strong>
                <small>{item.revisions.length} versões · {item.feedbacks.length} análises</small>
              </div>
              <Link
                to={studyPath(DEFAULT_COURSE_SLUG, item.lesson_number, 'revisar')}
              >
                Abrir texto
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="recordings-title">
        <p className="study-kicker">Speaking</p>
        <h2 id="recordings-title">Gravações mantidas</h2>
        {speakingQuery.isPending && <p className="muted">Carregando gravações…</p>}
        {speakingQuery.isError && <p className="erro">Não foi possível carregar as gravações.</p>}
        {speakingQuery.data?.length === 0 && <p className="notebook-empty">Nenhuma gravação salva na conta.</p>}
        <ul className="notebook-recordings">
          {speakingQuery.data?.map((attempt) => (
            <li key={attempt.id}>
              <div>
                <span>Aula {attempt.lesson_number}</span>
                <strong lang="en">{attempt.cue_text}</strong>
                <small>{Math.ceil(attempt.duration_ms / 1000)}s · {new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short' }).format(new Date(attempt.created_at))}</small>
              </div>
              <button type="button" onClick={() => void playRecording(attempt.id)}>Ouvir</button>
              <button type="button" onClick={() => void deleteRecording(attempt.id)}>Excluir</button>
            </li>
          ))}
        </ul>
        {recordingUrl && playingAttemptId !== null && (
          <audio aria-label="Gravação do caderno" controls autoPlay src={recordingUrl} />
        )}
      </section>
    </div>
  )
}
