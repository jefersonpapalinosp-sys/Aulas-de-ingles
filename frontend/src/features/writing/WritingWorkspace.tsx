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
import { AssistQuota } from '../assist/AssistQuota'
import { wordDiff } from './wordDiff'
import { WritingFeedbackProvenance } from './WritingFeedbackProvenance'
import { readLocal, removeLocal, writeLocal } from '../../storage/local'
import { invalidateStudy } from '../../api/invalidateStudy'

type SaveStatus = 'idle' | 'saving' | 'saved' | 'local' | 'unsaved'

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
  const revisionScope = `${userId}:${prompt.id}`
  const [revisionHistory, setRevisionHistory] = useState<{
    scope: string
    items: WritingRevision[]
    cursor?: string
  }>({ scope: revisionScope, items: [] })
  const revisionCursor = revisionHistory.scope === revisionScope
    ? revisionHistory.cursor
    : undefined
  const revisionLoadingMore = useRef(false)
  const revisionStatusRef = useRef<HTMLParagraphElement>(null)
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
  const versionsQuery = useQuery({
    queryKey: ['writing-versions', userId, prompt.id, revisionCursor || 'first'],
    queryFn: async () => {
      const { data } = await api.GET('/api/writing/prompts/{prompt_id}/versions', {
        params: {
          path: { prompt_id: prompt.id },
          query: { limit: 20, cursor: revisionCursor },
        },
      })
      if (!data || !Array.isArray(data.items)) {
        throw new Error('Não foi possível carregar as versões.')
      }
      return data
    },
    retry: false,
  })
  const [text, setText] = useState('')
  const [hydrated, setHydrated] = useState(false)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [storageWarning, setStorageWarning] = useState('')
  const localText = useRef<string | null>(null)
  const [feedback, setFeedback] = useState<WritingFeedback | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [creatingVersion, setCreatingVersion] = useState(false)
  const [actionMessage, setActionMessage] = useState('')
  const [comparison, setComparison] = useState<WritingRevision | null>(null)
  const [useAssisted, setUseAssisted] = useState(false)
  const textRef = useRef('')
  const lastQueued = useRef('')
  const saveQueue = useRef<Promise<void>>(Promise.resolve())
  const revision = useRef<number | null>(null)
  const epoch = useRef(0)
  const edits = useRef(0)
  const analysisRequest = useRef<{ payload: string; key: string } | null>(null)
  const conflictRef = useRef<WritingDraft | null>(null)
  const [conflict, setConflict] = useState<WritingDraft | null>(null)
  const [recovered, setRecovered] = useState(false)
  const [bothTexts, setBothTexts] = useState('')

  useEffect(() => {
    epoch.current += 1
    analysisRequest.current = null
    revision.current = null
    conflictRef.current = null
    setConflict(null)
    setBothTexts('')
    saveQueue.current = Promise.resolve()
    setHydrated(false)
    setFeedback(null)
    setComparison(null)
    setActionMessage('')
    setAnalyzing(false)
    setCreatingVersion(false)
    setRevisionHistory({ scope: `${userId}:${prompt.id}`, items: [] })
    revisionLoadingMore.current = false
    return () => { epoch.current += 1 }
  }, [prompt.id, userId])

  useEffect(() => {
    const result = versionsQuery.data
    if (!result) return
    setRevisionHistory((current) => ({
      scope: revisionScope,
      items:
        current.scope === revisionScope && revisionCursor
          ? [...current.items, ...result.items]
          : result.items,
      cursor: revisionCursor,
    }))
    if (revisionLoadingMore.current) {
      revisionLoadingMore.current = false
      window.requestAnimationFrame(() => revisionStatusRef.current?.focus())
    }
  }, [revisionCursor, revisionScope, versionsQuery.data])

  useEffect(() => {
    if (hydrated || (draftQuery.isPending && !draftQuery.isError)) return
    const remote = draftQuery.data?.text ?? ''
    const result = readLocal(key)
    const backup = result.ok ? result.value : null
    localText.current = backup
    setStorageWarning(result.ok ? '' : `${result.error} Pode existir um rascunho local mais recente.`)
    const initial = backup ?? remote
    revision.current = draftQuery.data ? (draftQuery.data.revision ?? 0) : null
    setRecovered(backup !== null)
    const metadata = readLocal(`${key}:revision`)
    const base = metadata.ok && metadata.value !== null ? Number(metadata.value) : null
    if (backup !== null && backup !== remote && draftQuery.data &&
        (base !== revision.current || base === null)) {
      conflictRef.current = draftQuery.data
      setConflict(draftQuery.data)
    }
    textRef.current = initial
    lastQueued.current = remote
    setText(initial)
    setSaveStatus(draftQuery.isError ? (backup !== null ? 'local' : 'unsaved') : 'idle')
    setHydrated(true)
  }, [draftQuery.data, draftQuery.isError, draftQuery.isPending, hydrated, key])

  const saveDraft = useCallback(
    (value: string) => {
      const generation = epoch.current
      setSaveStatus('saving')
      saveQueue.current = saveQueue.current
        .catch(() => undefined)
        .then(async () => {
          if (generation !== epoch.current || conflictRef.current) return
          let expectedRevision = revision.current
          if (expectedRevision === null) {
            const { data: remote } = await api.GET('/api/writing/prompts/{prompt_id}/draft', {
              params: { path: { prompt_id: prompt.id } },
            })
            if (!remote) throw new Error('Sem versão confirmada.')
            if (generation !== epoch.current) return
            if (remote.text !== value) {
              conflictRef.current = remote
              setConflict(remote)
              setSaveStatus('local')
              return
            }
            expectedRevision = remote.revision ?? 0
            revision.current = expectedRevision
          }
          const { data, error, response } = await api.PUT('/api/writing/prompts/{prompt_id}/draft', {
            params: { path: { prompt_id: prompt.id } },
            body: { text: value, expected_revision: expectedRevision },
          })
          if (generation !== epoch.current) return
          if (response?.status === 409) {
            const current = (error as { detail?: { current?: WritingDraft } })?.detail?.current
            if (current) {
              conflictRef.current = current
              setConflict(current)
            }
            throw new Error('Conflito de rascunho.')
          }
          if (!data) throw new Error('Falha ao salvar o rascunho.')
          revision.current = data.revision ?? 0
          queryClient.setQueryData<WritingDraft>(queryKey, data)
          if (textRef.current === value) {
            const stored = readLocal(key)
            // Uma confirmação desta aba não apaga o texto diferente de outra.
            const removed = !stored.ok ? stored : stored.value !== value ? { ok: true as const } : removeLocal(key)
            if (removed.ok) localText.current = null
            setStorageWarning(removed.ok ? '' : removed.error)
            setSaveStatus('saved')
            if (stored.ok && stored.value === value) removeLocal(`${key}:revision`)
          } else {
            // O próximo texto local deriva do save confirmado, não da revisão anterior.
            const stored = readLocal(key)
            if (stored.ok && stored.value === textRef.current) writeLocal(`${key}:revision`, String(revision.current))
          }
        })
        .catch(() => {
          if (generation !== epoch.current) return
          if (textRef.current === value) {
            lastQueued.current = ''
            setSaveStatus(localText.current === value ? 'local' : 'unsaved')
          }
        })
      return saveQueue.current
    },
    [key, prompt.id, queryClient, queryKey],
  )

  useEffect(() => {
    if (!hydrated || conflict || text === lastQueued.current) return
    const timer = window.setTimeout(() => {
      lastQueued.current = text
      void saveDraft(text)
    }, 700)
    return () => window.clearTimeout(timer)
  }, [hydrated, conflict, saveDraft, text])

  function changeText(value: string) {
    edits.current += 1
    textRef.current = value
    setText(value)
    setFeedback(null)
    setActionMessage('')
    const result = writeLocal(key, value)
    if (revision.current !== null) writeLocal(`${key}:revision`, String(revision.current))
    localText.current = result.ok ? value : null
    setStorageWarning(result.ok ? '' : `${result.error} Copie o texto antes de sair.`)
    setSaveStatus(result.ok ? 'local' : 'unsaved')
  }

  async function analyze() {
    // A análise é sobre um rascunho que a conta já conhece. Enquanto ele não
    // foi confirmado, o texto fica na tela e a análise espera — o corpo do
    // feedback não carrega revisão, mas analisar um rascunho inexistente
    // produziria histórico sem origem.
    if (revision.current === null) {
      setActionMessage('Confirme o rascunho na conta antes de analisar. Seu texto continua nesta tela.')
      return
    }
    const generation = epoch.current
    const edit = edits.current
    setAnalyzing(true)
    setActionMessage('')
    try {
      const assisted = Boolean(assistStatus.data?.writing_enabled && useAssisted)
      const payload = JSON.stringify([userId, prompt.id, text, assisted])
      if (analysisRequest.current?.payload !== payload)
        analysisRequest.current = { payload, key: crypto.randomUUID() }
      const { data, response } = await api.POST('/api/writing/prompts/{prompt_id}/feedback', {
        params: { path: { prompt_id: prompt.id } },
        // O feedback não compara revisão: o texto analisado vai no corpo. A
        // `operation_key` é que evita uma segunda cobrança no reenvio.
        body: { text, assisted, operation_key: analysisRequest.current.key },
      })
      if (response?.status === 409) {
        if (generation === epoch.current && edit === edits.current)
          setActionMessage('Análise já iniciada. Consulte o histórico antes de reenviar; seu texto foi mantido.')
        return
      }
      if (!data) throw new Error('Falha ao analisar o texto.')
      if (generation === epoch.current && edit === edits.current) {
        setFeedback(data)
        analysisRequest.current = null
      }
      await invalidateStudy(queryClient, 'writingFeedback')
    } catch {
      if (generation === epoch.current && edit === edits.current)
        setActionMessage('Análise indisponível; confira o estado de salvamento antes de sair.')
    } finally {
      if (generation === epoch.current) setAnalyzing(false)
      await invalidateStudy(queryClient, 'assistUsage')
    }
  }

  async function rateFeedback(rating: 'helpful' | 'not_helpful') {
    if (!feedback || feedback.analysis_mode !== 'assisted') return
    const generation = epoch.current
    const edit = edits.current
    const { data } = await api.PUT('/api/writing/feedback/{feedback_id}/rating', {
      params: { path: { feedback_id: feedback.id } },
      body: { rating },
    })
    if (generation !== epoch.current || edit !== edits.current) return
    if (!data) {
      setActionMessage('Não foi possível salvar sua avaliação do feedback.')
      return
    }
    setFeedback(data)
    setActionMessage('Obrigado. Esta avaliação será usada antes de ampliar o experimento.')
    await invalidateStudy(queryClient, 'assistUsage')
  }

  async function createVersion() {
    if (!text.trim() || conflictRef.current || revision.current === null) return
    const generation = epoch.current
    const value = text
    setCreatingVersion(true)
    setActionMessage('')
    const operation = saveQueue.current.catch(() => undefined).then(async () => {
      // Lida aqui, não na chamada: o autosave anterior na fila pode ter avançado a revisão.
      const expectedRevision = revision.current
      if (generation !== epoch.current || conflictRef.current || expectedRevision === null) return
      const { data, error, response } = await api.POST('/api/writing/prompts/{prompt_id}/versions', {
        params: { path: { prompt_id: prompt.id } },
        body: { text: value, expected_revision: expectedRevision },
      })
      if (generation !== epoch.current) return
      if (response?.status === 409) {
        const current = (error as { detail?: { current?: WritingDraft } })?.detail?.current
        if (current) { conflictRef.current = current; setConflict(current) }
      }
      if (!data) throw new Error('Falha ao criar a versão.')
      revision.current = data.draft_revision ?? revision.current
      queryClient.setQueryData<WritingDraft>(queryKey, (current) => ({
        prompt_id: prompt.id,
        revision: revision.current ?? 0,
        text: value,
        updated_at: current?.updated_at ?? null,
      }))
      setRevisionHistory((current) => ({
        scope: revisionScope,
        cursor: current.scope === revisionScope ? current.cursor : undefined,
        items: [
          data,
          ...(current.scope === revisionScope
            ? current.items.filter((item) => item.id !== data.id)
            : []),
        ],
      }))
      setActionMessage(`Versão ${data.version} criada.`)
    })
    saveQueue.current = operation.catch(() => {
      if (generation === epoch.current) setActionMessage('Não foi possível criar a versão. O rascunho não foi perdido.')
    }).finally(() => { if (generation === epoch.current) setCreatingVersion(false) })
    await saveQueue.current
  }

  function resolveConflict(useRemote: boolean) {
    const remote = conflictRef.current
    if (!remote) return
    revision.current = remote.revision ?? 0
    conflictRef.current = null
    setConflict(null)
    setBothTexts('')
    queryClient.setQueryData(queryKey, remote)
    if (useRemote) {
      changeText(remote.text)
      lastQueued.current = remote.text
      setSaveStatus('saved')
      const removed = removeLocal(key)
      if (removed.ok) localText.current = null
      setStorageWarning(removed.ok ? '' : removed.error)
    } else {
      lastQueued.current = textRef.current
      void saveDraft(textRef.current)
    }
  }

  const wordCount = countWords(text)
  const sentenceCount = countSentences(text)
  const revisions = revisionHistory.scope === revisionScope ? revisionHistory.items : []
  const nextRevisionCursor = versionsQuery.data?.next_cursor ?? undefined
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
      <div className="writing-meta">
        <span>{wordCount} palavras · {sentenceCount} frases</span>
        <span role="status" className={saveStatus === 'local' || saveStatus === 'unsaved' ? 'failed' : ''}>
          {!hydrated || draftQuery.isPending
            ? 'Carregando rascunho…'
            : saveStatus === 'saving'
              ? 'Salvando…'
              : saveStatus === 'saved'
                ? 'Rascunho salvo.'
                : saveStatus === 'local'
                  ? 'Salvo neste dispositivo; sincronização pendente.'
                  : saveStatus === 'unsaved'
                    ? 'Texto apenas nesta tela; salvamento não confirmado. Não feche a página.'
                  : 'Pronto para escrever.'}
        </span>
      </div>
      {storageWarning && <p role="alert" className="erro">{storageWarning}</p>}
      {recovered && <p>Rascunho recuperado neste dispositivo. Confira a sincronização com sua conta.</p>}
      {conflict && (
        <section className="writing-conflict" aria-labelledby="draft-conflict-title">
          <div role="alert"><h3 id="draft-conflict-title">Há duas versões do rascunho</h3></div>
          <p>O texto do editor continua neste dispositivo. A conta possui a revisão {conflict.revision ?? 0},
            salva em {conflict.updated_at ? new Date(conflict.updated_at).toLocaleString() : 'data não informada'}.</p>
          <label>Texto salvo na conta<textarea readOnly value={conflict.text} /></label>
          <div className="writing-actions">
            <button type="button" onClick={() => resolveConflict(false)}>Manter meu texto</button>
            <button type="button" onClick={() => resolveConflict(true)}>Usar texto da conta</button>
            <button type="button" onClick={() => setBothTexts(`Neste dispositivo:\n${text}\n\nNa conta:\n${conflict.text}`)}>Preparar cópia dos dois</button>
          </div>
          {bothTexts && <label>Selecione e copie os dois textos<textarea readOnly value={bothTexts} onFocus={(event) => event.target.select()} /></label>}
        </section>
      )}

      <div className="writing-actions">
        <button
          type="button"
          className="btn"
          disabled={!hydrated || analyzing || revision.current === null}
          onClick={() => void analyze()}
        >
          {analyzing ? 'Analisando…' : 'Analisar texto'}
        </button>
        <button
          type="button"
          className="btn ghost"
          disabled={!text.trim() || creatingVersion || Boolean(conflict) || revision.current === null}
          onClick={() => void createVersion()}
        >
          {creatingVersion ? 'Criando…' : 'Criar versão'}
        </button>
        {!conflict && (saveStatus === 'local' || saveStatus === 'unsaved') && (
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
            sendo aplicada.
          </span>
        </label>
      )}
      {actionMessage && <p className="writing-message" role="status">{actionMessage}</p>}
      {assistStatus.data?.writing_enabled && <AssistQuota status={assistStatus.data} />}

      {feedback && (
        <div className={`writing-feedback ${feedback.ready ? 'ready' : ''}`} aria-live="polite">
          <p className="assist-label">
            {feedback.analysis_mode === 'assisted'
              ? `Automatizado por ${feedback.provider} · somente avaliação`
              : feedback.analysis_mode === 'fallback'
                ? 'Assistência indisponível · rubrica local preservada'
                : 'Análise automática por regras locais'}
          </p>
          <h3>{feedback.ready ? 'Critérios automáticos atendidos' : 'O que revisar agora'}</h3>
          <WritingFeedbackProvenance feedback={feedback} />
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

      {versionsQuery.isPending && revisions.length === 0 && <p>Carregando versões…</p>}
      {versionsQuery.isError && revisions.length === 0 && (
        <p role="alert">Não foi possível carregar as versões salvas.</p>
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
          {nextRevisionCursor && (
            <button
              type="button"
              disabled={versionsQuery.isFetching}
              onClick={() => {
                revisionLoadingMore.current = true
                setRevisionHistory((current) => ({
                  ...current,
                  scope: revisionScope,
                  cursor: nextRevisionCursor,
                }))
              }}
            >
              {versionsQuery.isFetching ? 'Carregando mais…' : 'Carregar mais versões'}
            </button>
          )}
          <p ref={revisionStatusRef} tabIndex={-1} role="status">
            {revisions.length} {revisions.length === 1 ? 'versão carregada' : 'versões carregadas'}.
          </p>
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
