import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { api, type WritingFeedback, type WritingPrompt, type WritingRevision } from '../../api/client'
import { useAssistStatus } from '../../api/assist'
import { useWritingDraftSync } from '../../api/writing'
import { AssistQuota } from '../assist/AssistQuota'
import { DraftConflictPanel } from './DraftConflictPanel'
import { WritingEditor } from './WritingEditor'
import { WritingFeedbackPanel } from './WritingFeedbackPanel'
import { WritingDiff, WritingVersions } from './WritingVersions'
import { invalidateStudy } from '../../api/invalidateStudy'

/** Orquestra a atividade de escrita.
 *
 * O rascunho não mora mais aqui: fila, revisão, espelho local e conflito são do
 * `DraftSync` (`features/writing/draftSync.ts`), provado sem DOM. O que resta
 * neste componente é o que depende da tela — a análise, o histórico de versões
 * e a comparação.
 */
export function WritingWorkspace({ prompt, userId }: { prompt: WritingPrompt; userId: number }) {
  const queryClient = useQueryClient()
  const assistStatus = useAssistStatus(userId)
  const draft = useWritingDraftSync(prompt.id, userId)
  const revisionScope = `${userId}:${prompt.id}`
  const [revisionHistory, setRevisionHistory] = useState<{
    scope: string
    items: WritingRevision[]
    cursor?: string
  }>({ scope: revisionScope, items: [] })
  const revisionCursor = revisionHistory.scope === revisionScope ? revisionHistory.cursor : undefined
  const revisionLoadingMore = useRef(false)
  const revisionStatusRef = useRef<HTMLParagraphElement>(null)
  const versionsQuery = useQuery({
    queryKey: ['writing-versions', userId, prompt.id, revisionCursor || 'first'],
    queryFn: async () => {
      const { data } = await api.GET('/api/writing/prompts/{prompt_id}/versions', {
        params: { path: { prompt_id: prompt.id }, query: { limit: 20, cursor: revisionCursor } },
      })
      if (!data || !Array.isArray(data.items)) throw new Error('Não foi possível carregar as versões.')
      return data
    },
    retry: false,
  })
  const [feedback, setFeedback] = useState<WritingFeedback | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [creatingVersion, setCreatingVersion] = useState(false)
  const [actionMessage, setActionMessage] = useState('')
  const [comparison, setComparison] = useState<WritingRevision | null>(null)
  const [useAssisted, setUseAssisted] = useState(false)
  // `epoch` muda de atividade; `edits` muda de texto. Uma resposta atrasada que
  // cruzar qualquer um dos dois não pode ser aplicada na tela do outro.
  const epoch = useRef(0)
  const edits = useRef(0)
  const analysisRequest = useRef<{ payload: string; key: string } | null>(null)

  useEffect(() => {
    epoch.current += 1
    analysisRequest.current = null
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
      items: current.scope === revisionScope && revisionCursor
        ? [...current.items, ...result.items]
        : result.items,
      cursor: revisionCursor,
    }))
    if (revisionLoadingMore.current) {
      revisionLoadingMore.current = false
      window.requestAnimationFrame(() => revisionStatusRef.current?.focus())
    }
  }, [revisionCursor, revisionScope, versionsQuery.data])

  function changeText(value: string) {
    edits.current += 1
    draft.change(value)
    setFeedback(null)
    setActionMessage('')
  }

  async function analyze() {
    // A análise é sobre um rascunho que a conta já conhece. Enquanto ele não
    // foi confirmado, o texto fica na tela e a análise espera — o corpo do
    // feedback não carrega revisão, mas analisar um rascunho inexistente
    // produziria histórico sem origem.
    if (draft.revision === null) {
      setActionMessage('Confirme o rascunho na conta antes de analisar. Seu texto continua nesta tela.')
      return
    }
    const generation = epoch.current
    const edit = edits.current
    setAnalyzing(true)
    setActionMessage('')
    try {
      const assisted = Boolean(assistStatus.data?.writing_enabled && useAssisted)
      const payload = JSON.stringify([userId, prompt.id, draft.text, assisted])
      if (analysisRequest.current?.payload !== payload)
        analysisRequest.current = { payload, key: crypto.randomUUID() }
      const { data, response } = await api.POST('/api/writing/prompts/{prompt_id}/feedback', {
        params: { path: { prompt_id: prompt.id } },
        // O feedback não compara revisão: o texto analisado vai no corpo. A
        // `operation_key` é que evita uma segunda cobrança no reenvio.
        body: { text: draft.text, assisted, operation_key: analysisRequest.current.key },
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
    const generation = epoch.current
    setCreatingVersion(true)
    setActionMessage('')
    try {
      const created = await draft.createVersion()
      if (generation !== epoch.current || !created) return
      setRevisionHistory((current) => ({
        scope: revisionScope,
        cursor: current.scope === revisionScope ? current.cursor : undefined,
        items: [created, ...(current.scope === revisionScope
          ? current.items.filter((item) => item.id !== created.id)
          : [])],
      }))
      setActionMessage(`Versão ${created.version} criada.`)
    } catch {
      if (generation === epoch.current)
        setActionMessage('Não foi possível criar a versão. O rascunho não foi perdido.')
    } finally {
      if (generation === epoch.current) setCreatingVersion(false)
    }
  }

  const revisions = revisionHistory.scope === revisionScope ? revisionHistory.items : []
  const pending = draft.status === 'local' || draft.status === 'unsaved'

  return (
    <section className="writing-workspace" aria-labelledby="writing-title">
      <WritingEditor
        prompt={prompt}
        text={draft.text}
        status={draft.status}
        hydrated={draft.hydrated}
        recovered={draft.recovered}
        storageWarning={draft.storageWarning}
        onChange={changeText}
      />
      {draft.conflict && (
        <DraftConflictPanel conflict={draft.conflict} text={draft.text} onResolve={draft.resolve} />
      )}

      <div className="writing-actions">
        <button
          type="button"
          className="btn"
          disabled={!draft.hydrated || analyzing || draft.revision === null}
          onClick={() => void analyze()}
        >
          {analyzing ? 'Analisando…' : 'Analisar texto'}
        </button>
        <button
          type="button"
          className="btn ghost"
          disabled={!draft.text.trim() || creatingVersion || Boolean(draft.conflict) || draft.revision === null}
          onClick={() => void createVersion()}
        >
          {creatingVersion ? 'Criando…' : 'Criar versão'}
        </button>
        {!draft.conflict && pending && (
          <button type="button" className="writing-retry" onClick={() => void draft.flush()}>
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
      {feedback && <WritingFeedbackPanel feedback={feedback} onRate={(rating) => void rateFeedback(rating)} />}

      <WritingVersions
        revisions={revisions}
        loading={versionsQuery.isPending}
        failed={versionsQuery.isError}
        fetching={versionsQuery.isFetching}
        nextCursor={versionsQuery.data?.next_cursor ?? undefined}
        statusRef={revisionStatusRef}
        onRestore={changeText}
        onCompare={setComparison}
        onLoadMore={(cursor) => {
          revisionLoadingMore.current = true
          setRevisionHistory((current) => ({ ...current, scope: revisionScope, cursor }))
        }}
      />
      {comparison && (
        <WritingDiff comparison={comparison} text={draft.text} onClose={() => setComparison(null)} />
      )}
    </section>
  )
}
