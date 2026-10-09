import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  api,
  type WritingDraft,
  type WritingFeedback,
  type WritingPrompt,
  type WritingRevision,
} from '../../api/client'
import { useAssistStatus } from '../../api/assist'
import { wordDiff } from './wordDiff'

type SaveStatus = 'idle' | 'saving' | 'saved' | 'local'

function backupKey(userId: number, promptId: number): string {
  return `aulas-ingles:writing-draft:v1:${userId}:${promptId}`
}

function countWords(text: string): number {
  return text.match(/[A-Za-z]+(?:['’][A-Za-z]+)?/g)?.length ?? 0
}

function countSentences(text: string): number {
  return text.match(/[^.!?]+[.!?]+|[^.!?]+$/g)?.filter((part) => part.trim()).length ?? 0
}

export function WritingWorkspace({
  prompt,
  userId,
}: {
  prompt: WritingPrompt
  userId: number
}) {
  const queryClient = useQueryClient()
  const assistStatus = useAssistStatus(userId)
  const key = useMemo(() => backupKey(userId, prompt.id), [prompt.id, userId])
  const queryKey = useMemo(() => ['writing-draft', userId, prompt.id] as const, [prompt.id, userId])
  const draftQuery = useQuery({
    queryKey,
    queryFn: async () => {
      const { data } = await api.GET('/api/writing/prompts/{prompt_id}/draft', {
        params: { path: { prompt_id: prompt.id } },
      })
      if (!data) throw new Error('Não foi possível carregar o rascunho.')
      return data
    },
    retry: false,
  })
  const [text, setText] = useState('')
  const [hydrated, setHydrated] = useState(false)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [feedback, setFeedback] = useState<WritingFeedback | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [creatingVersion, setCreatingVersion] = useState(false)
  const [actionMessage, setActionMessage] = useState('')
  const [comparison, setComparison] = useState<WritingRevision | null>(null)
  const [useAssisted, setUseAssisted] = useState(false)
  const textRef = useRef('')
  const lastQueued = useRef('')
  const saveQueue = useRef<Promise<void>>(Promise.resolve())

  useEffect(() => {
    setHydrated(false)
    setFeedback(null)
    setComparison(null)
    setActionMessage('')
  }, [prompt.id, userId])

  useEffect(() => {
    if (hydrated || (draftQuery.isPending && !draftQuery.isError)) return
    const remote = draftQuery.data?.text ?? ''
    const backup = window.localStorage.getItem(key)
    const initial = backup ?? remote
    textRef.current = initial
    lastQueued.current = remote
    setText(initial)
    setSaveStatus(draftQuery.isError ? 'local' : 'idle')
    setHydrated(true)
  }, [draftQuery.data, draftQuery.isError, draftQuery.isPending, hydrated, key])

  const saveDraft = useCallback(
    (value: string) => {
      setSaveStatus('saving')
      saveQueue.current = saveQueue.current
        .catch(() => undefined)
        .then(async () => {
          const { data } = await api.PUT('/api/writing/prompts/{prompt_id}/draft', {
            params: { path: { prompt_id: prompt.id } },
            body: { text: value },
          })
          if (!data) throw new Error('Falha ao salvar o rascunho.')
          queryClient.setQueryData<WritingDraft>(queryKey, data)
          if (textRef.current === value) {
            window.localStorage.removeItem(key)
            setSaveStatus('saved')
          }
        })
        .catch(() => {
          if (textRef.current === value) {
            lastQueued.current = ''
            setSaveStatus('local')
          }
        })
      return saveQueue.current
    },
    [key, prompt.id, queryClient, queryKey],
  )

  useEffect(() => {
    if (!hydrated || text === lastQueued.current) return
    const timer = window.setTimeout(() => {
      lastQueued.current = text
      void saveDraft(text)
    }, 700)
    return () => window.clearTimeout(timer)
  }, [hydrated, saveDraft, text])

  function changeText(value: string) {
    textRef.current = value
    setText(value)
    setFeedback(null)
    setActionMessage('')
    window.localStorage.setItem(key, value)
  }

  async function analyze() {
    setAnalyzing(true)
    setActionMessage('')
    try {
      const { data } = await api.POST('/api/writing/prompts/{prompt_id}/feedback', {
        params: { path: { prompt_id: prompt.id } },
        body: { text, assisted: Boolean(assistStatus.data?.writing_enabled && useAssisted) },
      })
      if (!data) throw new Error('Falha ao analisar o texto.')
      setFeedback(data)
      await queryClient.invalidateQueries({ queryKey: ['course-completion'] })
    } catch {
      setActionMessage('Não foi possível analisar agora. Seu texto continua salvo.')
    } finally {
      setAnalyzing(false)
    }
  }

  async function rateFeedback(rating: 'helpful' | 'not_helpful') {
    if (!feedback || feedback.analysis_mode !== 'assisted') return
    const { data } = await api.PUT('/api/writing/feedback/{feedback_id}/rating', {
      params: { path: { feedback_id: feedback.id } },
      body: { rating },
    })
    if (!data) {
      setActionMessage('Não foi possível salvar sua avaliação do feedback.')
      return
    }
    setFeedback(data)
    setActionMessage('Obrigado. Esta avaliação será usada antes de ampliar o experimento.')
    await queryClient.invalidateQueries({ queryKey: ['assist-status', userId] })
  }

  async function createVersion() {
    if (!text.trim()) return
    setCreatingVersion(true)
    setActionMessage('')
    try {
      await saveQueue.current
      const { data } = await api.POST('/api/writing/prompts/{prompt_id}/versions', {
        params: { path: { prompt_id: prompt.id } },
        body: { text },
      })
      if (!data) throw new Error('Falha ao criar a versão.')
      queryClient.setQueryData<WritingDraft>(queryKey, (current) => ({
        prompt_id: prompt.id,
        text,
        updated_at: current?.updated_at ?? null,
        revisions: [data, ...(current?.revisions.filter((item) => item.id !== data.id) ?? [])],
      }))
      setActionMessage(`Versão ${data.version} criada.`)
    } catch {
      setActionMessage('Não foi possível criar a versão. O rascunho não foi perdido.')
    } finally {
      setCreatingVersion(false)
    }
  }

  const wordCount = countWords(text)
  const sentenceCount = countSentences(text)
  const revisions = draftQuery.data?.revisions ?? []
  const comparisonParts = comparison ? wordDiff(comparison.text, text) : []

  return (
    <section className="writing-workspace" aria-labelledby="writing-title">
      <p className="study-kicker">Writing · produção guiada</p>
      <h2 id="writing-title">{prompt.title}</h2>
      <p className="writing-instructions" lang="en">
        {prompt.instructions}
      </p>
      <ul className="writing-targets" aria-label="Critérios da atividade">
        <li>{prompt.min_words}+ palavras</li>
        <li>{prompt.min_sentences}+ frases</li>
        {prompt.requirements.map((requirement) => (
          <li key={requirement.label}>{requirement.label}</li>
        ))}
      </ul>

      <label className="writing-editor">
        <span>Seu texto em inglês</span>
        <textarea
          value={text}
          maxLength={5000}
          disabled={!hydrated}
          placeholder="Write your first sentence here…"
          onChange={(event) => changeText(event.target.value)}
        />
      </label>
      <div className="writing-meta" aria-live="polite">
        <span>{wordCount} palavras · {sentenceCount} frases</span>
        <span className={saveStatus === 'local' ? 'failed' : ''}>
          {!hydrated || draftQuery.isPending
            ? 'Carregando rascunho…'
            : saveStatus === 'saving'
              ? 'Salvando…'
              : saveStatus === 'saved'
                ? 'Rascunho salvo.'
                : saveStatus === 'local'
                  ? 'Salvo neste dispositivo; sincronização pendente.'
                  : 'Pronto para escrever.'}
        </span>
      </div>

      <div className="writing-actions">
        <button
          type="button"
          className="btn"
          disabled={!hydrated || analyzing}
          onClick={() => void analyze()}
        >
          {analyzing ? 'Analisando…' : 'Analisar texto'}
        </button>
        <button
          type="button"
          className="btn ghost"
          disabled={!text.trim() || creatingVersion}
          onClick={() => void createVersion()}
        >
          {creatingVersion ? 'Criando…' : 'Criar versão'}
        </button>
        {saveStatus === 'local' && (
          <button
            type="button"
            className="writing-retry"
            onClick={() => {
              lastQueued.current = text
              void saveDraft(text)
            }}
          >
            Tentar sincronizar
          </button>
        )}
      </div>
      {assistStatus.data?.writing_enabled && (
        <label className="assist-opt-in">
          <input
            type="checkbox"
            checked={useAssisted}
            disabled={analyzing || assistStatus.data.remaining_today === 0}
            onChange={(event) => setUseAssisted(event.target.checked)}
          />
          <span>
            Experimentar feedback assistido automatizado. Pode errar; a rubrica local continua
            sendo aplicada. Restam {assistStatus.data.remaining_today} análises hoje.
          </span>
        </label>
      )}
      {actionMessage && <p className="writing-message" role="status">{actionMessage}</p>}

      {feedback && (
        <div className={`writing-feedback ${feedback.ready ? 'ready' : ''}`} aria-live="polite">
          <p className="assist-label">
            {feedback.analysis_mode === 'assisted'
              ? `Automatizado por ${feedback.provider} · somente avaliação`
              : feedback.analysis_mode === 'fallback'
                ? 'Assistência indisponível · rubrica local preservada'
                : 'Análise automática por regras locais'}
          </p>
          <h3>{feedback.ready ? 'Texto pronto para uma nova versão' : 'O que revisar agora'}</h3>
          <ul>
            {feedback.checks.map((check) => (
              <li key={check.code} className={check.passed ? 'passed' : ''}>
                <span aria-hidden="true">{check.passed ? '✓' : '○'}</span>
                <span>
                  <strong>{check.label}</strong>
                  {!check.passed && <small>{check.suggestion}</small>}
                </span>
              </li>
            ))}
          </ul>
          {feedback.assisted_summary && (
            <div className="assist-writing-copy">
              <strong>Comentário experimental</strong>
              <p>{feedback.assisted_summary}</p>
              {feedback.assisted_suggestions.length > 0 && (
                <ul>
                  {feedback.assisted_suggestions.map((suggestion, index) => (
                    <li key={`${String(suggestion.criterion)}-${index}`}>
                      <strong>{String(suggestion.criterion)}</strong>
                      <span>{String(suggestion.message)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {feedback.low_confidence && (
            <p className="assist-warning" role="alert">
              Baixa confiança: use este comentário como hipótese e confira pela rubrica.
            </p>
          )}
          {feedback.analysis_mode === 'assisted' && (
            <div className="assist-rating" aria-label="Avaliar feedback automático">
              <span>Este comentário ajudou?</span>
              <button
                type="button"
                aria-pressed={feedback.human_rating === 'helpful'}
                onClick={() => void rateFeedback('helpful')}
              >
                Sim
              </button>
              <button
                type="button"
                aria-pressed={feedback.human_rating === 'not_helpful'}
                onClick={() => void rateFeedback('not_helpful')}
              >
                Não
              </button>
            </div>
          )}
        </div>
      )}

      {revisions.length > 0 && (
        <div className="writing-history">
          <h3>Versões salvas</h3>
          <ul>
            {revisions.map((revision) => (
              <li key={revision.id}>
                <span>Versão {revision.version}</span>
                <time dateTime={revision.created_at}>
                  {new Intl.DateTimeFormat('pt-BR', {
                    dateStyle: 'short',
                    timeStyle: 'short',
                  }).format(new Date(revision.created_at))}
                </time>
                <button type="button" onClick={() => changeText(revision.text)}>
                  Restaurar no editor
                </button>
                <button type="button" onClick={() => setComparison(revision)}>
                  Comparar com texto atual
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {comparison && (
        <div className="writing-diff" aria-live="polite">
          <div className="writing-diff-head">
            <div>
              <p className="study-kicker">Comparação</p>
              <h3>Versão {comparison.version} → texto atual</h3>
            </div>
            <button type="button" onClick={() => setComparison(null)}>Fechar comparação</button>
          </div>
          <p className="writing-diff-legend">
            <span className="removed">Removido</span>
            <span className="added">Adicionado</span>
          </p>
          <p className="writing-diff-copy" lang="en">
            {comparisonParts.map((part, index) =>
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
      )}
    </section>
  )
}
