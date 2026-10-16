import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  api,
  authenticatedFetch,
  type NotebookEntry,
  type NotebookKind,
} from '../api/client'
import { useCourseCurriculum, useCourses } from '../api/queries'
import { curriculumLessons } from '../features/curriculum/curriculum'
import { HistoricalContentDetails } from '../features/history/HistoricalContentDetails'
import { WritingFeedbackProvenance } from '../features/writing/WritingFeedbackProvenance'
import { DEFAULT_COURSE_SLUG, studyPath } from '../routing/courseRoutes'
import { usePagedItems } from './usePagedItems'

const KINDS: readonly { value: NotebookKind; label: string }[] = [
  { value: 'note', label: 'Anotação livre' },
  { value: 'favorite_phrase', label: 'Frase favorita' },
  { value: 'personal_example', label: 'Exemplo pessoal' },
  { value: 'recurring_error', label: 'Erro recorrente' },
  { value: 'teacher_question', label: 'Pergunta ao professor' },
]
const SHORT_DATE = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short' })
const SHORT_DATE_TIME = new Intl.DateTimeFormat('pt-BR', {
  dateStyle: 'short',
  timeStyle: 'short',
})
const HISTORY_LABELS = {
  exercise: 'Exercício',
  practice: 'Prática guiada',
  writing: 'Correção de escrita',
  speaking: 'Tentativa de fala',
  checkpoint: 'Checkpoint',
} as const

function kindLabel(kind: NotebookKind): string {
  return KINDS.find((item) => item.value === kind)?.label ?? kind
}

function WritingFeedbackHistory({
  promptId,
  feedbackCount,
}: {
  promptId: number
  feedbackCount: number
}) {
  const [open, setOpen] = useState(false)
  const [cursor, setCursor] = useState<string>()
  const loadingMore = useRef(false)
  const statusRef = useRef<HTMLParagraphElement>(null)
  const query = useQuery({
    queryKey: ['writing-feedback-history', promptId, cursor || 'first'],
    queryFn: async () => {
      const { data } = await api.GET('/api/writing/prompts/{prompt_id}/feedback', {
        params: {
          path: { prompt_id: promptId },
          query: { limit: 20, cursor },
        },
      })
      if (!data) throw new Error('Não foi possível carregar as análises.')
      return data
    },
    enabled: open,
    retry: false,
  })
  const [items] = usePagedItems(query.data, cursor, loadingMore, statusRef)

  const nextCursor = query.data?.next_cursor ?? undefined
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
      {nextCursor && (
        <button
          type="button"
          disabled={query.isFetching}
          onClick={() => {
            loadingMore.current = true
            setCursor(nextCursor)
          }}
        >
          {query.isFetching ? 'Carregando mais…' : 'Carregar mais análises'}
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

export function NotebookPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const courseSlug = searchParams.get('course') || DEFAULT_COURSE_SLUG
  const unitSlug = searchParams.get('unit') || ''
  const courses = useCourses()
  const curriculum = useCourseCurriculum(courseSlug)
  const lessons = useMemo(
    () =>
      curriculumLessons(curriculum.data).filter(
        (lesson) => !unitSlug || lesson.unit_slug === unitSlug,
      ),
    [curriculum.data, unitSlug],
  )
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
  const [notebookCursor, setNotebookCursor] = useState<string>()
  const [writingCursor, setWritingCursor] = useState<string>()
  const [speakingCursor, setSpeakingCursor] = useState<string>()
  const [historyCursor, setHistoryCursor] = useState<string>()
  const writingLoadingMore = useRef(false)
  const writingStatusRef = useRef<HTMLParagraphElement>(null)
  const speakingLoadingMore = useRef(false)
  const speakingStatusRef = useRef<HTMLParagraphElement>(null)
  const historyLoadingMore = useRef(false)
  const historyStatusRef = useRef<HTMLParagraphElement>(null)
  const entriesQuery = useQuery({
    queryKey: [
      'notebook',
      courseSlug,
      unitSlug || 'all',
      lessonFilter,
      kindFilter,
      notebookCursor || 'first',
    ],
    queryFn: async () => {
      const { data } = await api.GET('/api/me/notebook/page', {
        params: {
          query: {
            lesson: lessonFilter === 'all' ? undefined : lessonFilter,
            kind: kindFilter === 'all' ? undefined : kindFilter,
            course: courseSlug,
            unit: unitSlug || undefined,
            limit: 20,
            cursor: notebookCursor,
          },
        },
      })
      if (!data) throw Error()
      return data
    },
    retry: false,
  })
  const nextNotebookCursor = entriesQuery.data?.next_cursor ?? undefined
  const writingQuery = useQuery({
    queryKey: ['writing-history', courseSlug, unitSlug || 'all', writingCursor || 'first'],
    queryFn: async () => {
      const { data } = await api.GET('/api/writing/history/page', {
        params: {
          query: {
            course: courseSlug,
            unit: unitSlug || undefined,
            limit: 20,
            cursor: writingCursor,
          },
        },
      })
      if (!data) throw Error()
      return data
    },
    retry: false,
  })
  const nextWritingCursor = writingQuery.data?.next_cursor ?? undefined
  const speakingQuery = useQuery({
    queryKey: [
      'speaking-attempts-page',
      courseSlug,
      unitSlug || 'all',
      speakingCursor || 'first',
    ],
    queryFn: async () => {
      const { data } = await api.GET('/api/speaking/attempts/page', {
        params: {
          query: {
            course: courseSlug,
            unit: unitSlug || undefined,
            limit: 20,
            cursor: speakingCursor,
          },
        },
      })
      if (!data) throw Error()
      return data
    },
    retry: false,
  })
  const historyQuery = useQuery({
    queryKey: ['historical-evidence-page', historyCursor || 'first'],
    queryFn: async () => {
      const { data } = await api.GET('/api/me/history/page', {
        params: { query: { limit: 20, cursor: historyCursor } },
      })
      if (!data) throw Error()
      return data
    },
    retry: false,
  })
  const [notebookEntries, setNotebookEntries] = usePagedItems(
    entriesQuery.data,
    notebookCursor,
  )
  const [writingEntries, setWritingEntries] = usePagedItems(
    writingQuery.data,
    writingCursor,
    writingLoadingMore,
    writingStatusRef,
  )
  const [speakingEntries, setSpeakingEntries] = usePagedItems(
    speakingQuery.data,
    speakingCursor,
    speakingLoadingMore,
    speakingStatusRef,
  )
  const [historicalEvidence] = usePagedItems(
    historyQuery.data,
    historyCursor,
    historyLoadingMore,
    historyStatusRef,
  )

  useEffect(
    () => () => {
      if (recordingUrl) URL.revokeObjectURL(recordingUrl)
    },
    [recordingUrl],
  )

  useEffect(() => {
    if (!lessons.some((lesson) => lesson.number === lessonNumber)) {
      setLessonNumber(lessons[0]?.number ?? 0)
    }
  }, [lessonNumber, lessons])

  function setScope(nextCourse: string, nextUnit = '') {
    const next = new URLSearchParams(searchParams)
    next.set('course', nextCourse)
    if (nextUnit) next.set('unit', nextUnit)
    else next.delete('unit')
    setSearchParams(next, { replace: true })
    setLessonFilter('all')
    setLessonNumber(0)
    setEditing(null)
    setMessage('')
    resetNotebookPagination()
    setWritingEntries([])
    setWritingCursor(undefined)
    writingLoadingMore.current = false
    setSpeakingEntries([])
    setSpeakingCursor(undefined)
    speakingLoadingMore.current = false
  }

  function resetNotebookPagination() {
    setNotebookEntries([])
    setNotebookCursor(undefined)
  }

  function refreshNotebook() {
    if (notebookCursor) setNotebookCursor(undefined)
    else void entriesQuery.refetch()
  }

  async function createEntry() {
    if (!content.trim() || lessonNumber === 0) return
    setSaving(true)
    setMessage('')
    try {
      const { data } = await api.POST('/api/me/notebook', {
        body: { course_slug: courseSlug, lesson_number: lessonNumber, kind, content },
      })
      if (!data) throw Error()
      setContent('')
      setMessage('Anotação salva no seu caderno.')
      refreshNotebook()
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
      if (!data) throw Error()
      setEditing(null)
      setMessage('Anotação atualizada.')
      refreshNotebook()
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
    refreshNotebook()
  }

  async function exportData() {
    setExporting(true)
    setMessage('')
    try {
      const response = await authenticatedFetch('/api/me/export')
      if (!response.ok) throw Error()
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
      if (!response.ok) throw Error()
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
    setSpeakingEntries((current) => current.filter((attempt) => attempt.id !== attemptId))
  }

  return (
    <div className="notebook-page">
      <header className="notebook-header">
        <div>
          <p className="eyebrow">Seu espaço privado</p>
          <h1>Caderno de inglês</h1>
        </div>
        <button type="button" className="btn ghost" disabled={exporting} onClick={() => void exportData()}>
          {exporting ? 'Exportando…' : 'Exportar meus dados'}
        </button>
      </header>
      <p className="notebook-privacy">
        As anotações são privadas e não alteram as aulas.
        {' '}<Link to="/meus-dados">Meus dados e áudios</Link>
      </p>
      <div className="notebook-filters" aria-label="Escopo do caderno">
        <label>
          Curso
          <select value={courseSlug} onChange={(event) => setScope(event.target.value)}>
            {(courses.data ?? []).map((course) => (
              <option key={course.slug} value={course.slug}>
                {course.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          Unidade
          <select
            value={unitSlug}
            onChange={(event) => setScope(courseSlug, event.target.value)}
          >
            <option value="">Todas as unidades</option>
            {(curriculum.data?.units ?? []).map((unit) => (
              <option key={unit.slug} value={unit.slug}>
                {unit.title}
              </option>
            ))}
          </select>
        </label>
      </div>
      {message && <p className="notebook-message" role="status">{message}</p>}

      <section className="notebook-compose" aria-labelledby="new-note-title">
        <p className="study-kicker">Nova entrada</p>
        <h2 id="new-note-title">O que você quer lembrar?</h2>
        <div className="notebook-fields">
          <label>
            Aula
            <select value={lessonNumber} onChange={(event) => setLessonNumber(Number(event.target.value))}>
              {lessons.length === 0 && <option value={0}>Nenhuma aula publicada</option>}
              {lessons.map((lesson) => (
                <option key={`${lesson.course_slug}:${lesson.number}`} value={lesson.number}>
                  Aula {lesson.number} · {lesson.title}
                </option>
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
          <button
            type="button"
            className="btn"
            disabled={saving || lessonNumber === 0 || !content.trim()}
            onClick={() => void createEntry()}
          >
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
              <select value={lessonFilter} onChange={(event) => {
                resetNotebookPagination()
                setLessonFilter(event.target.value === 'all' ? 'all' : Number(event.target.value))
              }}>
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
              <select value={kindFilter} onChange={(event) => {
                resetNotebookPagination()
                setKindFilter(event.target.value as 'all' | NotebookKind)
              }}>
                <option value="all">Todos</option>
                {KINDS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
            </label>
          </div>
        </div>
        {entriesQuery.isPending && <p className="muted">Carregando caderno…</p>}
        {entriesQuery.isError && <p className="erro">Não foi possível carregar o caderno.</p>}
        {!entriesQuery.isPending && notebookEntries.length === 0 && <p className="notebook-empty">Nenhuma anotação com estes filtros.</p>}
        <ul className="notebook-list">
          {notebookEntries.map((entry) => (
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
                    <span>{entry.course_title} · Aula {entry.lesson_number}</span>
                    <time dateTime={entry.updated_at}>{SHORT_DATE_TIME.format(new Date(entry.updated_at))}</time>
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
        {nextNotebookCursor && (
          <button
            type="button"
            className="btn ghost"
            disabled={entriesQuery.isFetching}
            onClick={() => setNotebookCursor(nextNotebookCursor)}
          >
            {entriesQuery.isFetching ? 'Carregando mais…' : 'Carregar mais anotações'}
          </button>
        )}
      </section>

      <section aria-labelledby="texts-title">
        <p className="study-kicker">Writing</p>
        <h2 id="texts-title">Textos e correções</h2>
        {writingQuery.isPending && <p className="muted">Carregando textos…</p>}
        {writingQuery.isError && <p className="erro">Não foi possível carregar os textos.</p>}
        {writingEntries.length === 0 && !writingQuery.isPending && !writingQuery.isError && (
          <p className="notebook-empty">Você ainda não começou uma produção escrita.</p>
        )}
        <ul className="notebook-writing-list">
          {writingEntries.map((item) => (
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
              <Link
                to={studyPath(item.course_slug, item.lesson_number, 'revisar')}
              >
                Abrir texto
              </Link>
            </li>
          ))}
        </ul>
        {nextWritingCursor && (
          <button
            type="button"
            className="btn ghost"
            disabled={writingQuery.isFetching}
            onClick={() => {
              writingLoadingMore.current = true
              setWritingCursor(nextWritingCursor)
            }}
          >
            {writingQuery.isFetching ? 'Carregando mais…' : 'Carregar mais textos'}
          </button>
        )}
        {writingEntries.length > 0 && (
          <p ref={writingStatusRef} tabIndex={-1} role="status" className="muted">
            {writingEntries.length} textos carregados.
          </p>
        )}
      </section>

      <section aria-labelledby="recordings-title">
        <p className="study-kicker">Speaking</p>
        <h2 id="recordings-title">Gravações mantidas</h2>
        {speakingQuery.isPending && speakingEntries.length === 0 && (
          <p className="muted">Carregando gravações…</p>
        )}
        {speakingQuery.isError && <p className="erro">Não foi possível carregar as gravações.</p>}
        {speakingEntries.length === 0 && !speakingQuery.isPending && !speakingQuery.isError && (
          <p className="notebook-empty">Nenhuma gravação salva na conta.</p>
        )}
        <ul className="notebook-recordings">
          {speakingEntries.map((attempt) => (
            <li key={attempt.id}>
              <div>
                <span>{attempt.course_title} · Aula {attempt.lesson_number}</span>
                {attempt.cue_text ? (
                  <strong lang="en">{attempt.cue_text}</strong>
                ) : (
                  <strong>Texto original indisponível</strong>
                )}
                <small>{Math.ceil(attempt.duration_ms / 1000)}s · {SHORT_DATE.format(new Date(attempt.created_at))}</small>
              </div>
              <button type="button" onClick={() => void playRecording(attempt.id)}>Ouvir</button>
              <button type="button" onClick={() => void deleteRecording(attempt.id)}>Excluir</button>
            </li>
          ))}
        </ul>
        {speakingQuery.data?.next_cursor && (
          <button
            type="button"
            className="btn ghost"
            disabled={speakingQuery.isFetching}
            onClick={() => {
              speakingLoadingMore.current = true
              setSpeakingCursor(speakingQuery.data?.next_cursor ?? undefined)
            }}
          >
            {speakingQuery.isFetching ? 'Carregando mais…' : 'Carregar mais gravações'}
          </button>
        )}
        {speakingEntries.length > 0 && (
          <p ref={speakingStatusRef} tabIndex={-1} role="status" className="muted">
            {speakingEntries.length} gravações carregadas.
          </p>
        )}
        {recordingUrl && playingAttemptId !== null && (
          <audio aria-label="Gravação do caderno" controls autoPlay src={recordingUrl} />
        )}
      </section>

      <section aria-labelledby="historical-content-title">
        <p className="study-kicker">Memória do conteúdo</p>
        <h2 id="historical-content-title">Conteúdo histórico preservado</h2>
        <p className="muted">
          Evidências capturadas em todos os cursos permanecem consultáveis mesmo se o conteúdo
          atual mudar ou for arquivado. Por isso, esta lista não cria links para a aula atual e
          não é afetada pelos filtros acima.
        </p>
        {historyQuery.isPending && historicalEvidence.length === 0 && (
          <p className="muted">Carregando conteúdo histórico…</p>
        )}
        {historyQuery.isError && (
          <p className="erro">Não foi possível carregar o conteúdo histórico.</p>
        )}
        {historicalEvidence.length === 0 && !historyQuery.isPending && !historyQuery.isError && (
          <p className="notebook-empty">Nenhum conteúdo foi capturado nas evidências desta conta.</p>
        )}
        <ul className="notebook-history-list">
          {historicalEvidence.map((item) => (
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
        {historyQuery.data?.next_cursor && (
          <button
            type="button"
            className="btn ghost"
            disabled={historyQuery.isFetching}
            onClick={() => {
              historyLoadingMore.current = true
              setHistoryCursor(historyQuery.data?.next_cursor ?? undefined)
            }}
          >
            {historyQuery.isFetching ? 'Carregando mais…' : 'Carregar mais conteúdo histórico'}
          </button>
        )}
        {historicalEvidence.length > 0 && (
          <p ref={historyStatusRef} tabIndex={-1} role="status" className="muted">
            {historicalEvidence.length} evidências históricas carregadas.
          </p>
        )}
      </section>
    </div>
  )
}
