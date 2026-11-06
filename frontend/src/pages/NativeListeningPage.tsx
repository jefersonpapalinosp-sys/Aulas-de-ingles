import { useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSessao } from '../api/auth'
import { api } from '../api/client'
import { ApiError } from '../api/errors'
import { READ_POLICY } from '../api/readPolicy'
import { startNative, type NativeResponse, type NativeSession } from '../api/nativeListening'
import { nativeStore, type NativeDraft } from '../features/listening/nativeStore'
import { readNativeSession, resolveNative } from '../features/listening/nativeQueue'
import { useNativeLocal } from '../features/listening/useNativeLocal'
import { useOnline } from '../features/offline/useOnline'
import { SelectionInput } from '../features/exercise/SelectionInput'
import { NativeAudioPlayer } from '../features/media/NativeAudioPlayer'
import '../styles/listening.css'

const EMPTY_IDS: string[] = []

export function NativeListeningPage() {
  const { usuario } = useSessao()
  const { slug = '' } = useParams()
  return <NativePractice key={`${usuario?.id}:${slug}`} slug={slug} userId={usuario?.id ?? 0} />
}

function NativePractice({ slug, userId }: { slug: string; userId: number }) {
  const { offline } = useSessao()
  const online = useOnline()
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const sessionId = Number(params.get('sessao'))
  const invalidSession = params.has('sessao') && (!Number.isSafeInteger(sessionId) || sessionId <= 0)
  const [startKey] = useState(() => crypto.randomUUID())
  const device = useNativeLocal(userId, online, offline)
  const [saving, setSaving] = useState(false)
  const [onlyErrors, setOnlyErrors] = useState(params.get('erros') === '1')
  const detail = useQuery({ queryKey: ['native-listening-detail', userId, slug], ...READ_POLICY,
    queryFn: async () => {
      const { data, response } = await api.GET('/api/listening/native/{slug}', { params: { path: { slug } } })
      if (!data) throw new ApiError('a atividade', response)
      return data
    },
  })
  const session = useQuery({ queryKey: ['native-listening-session', userId, sessionId], ...READ_POLICY,
    enabled: Number.isSafeInteger(sessionId) && sessionId > 0 && online && !offline,
    queryFn: async () => {
      const local = await nativeStore.read(userId).catch(() => null)
      const data = await readNativeSession(sessionId)
      if (data.activity.slug !== slug) throw new Error('A sessão pertence a outra atividade.')
      if (local) await nativeStore.cache(userId, local.epoch, data).catch(error => device.setError(String(error)))
      return data
    },
  })
  const accept = async (data: NativeSession) => {
    if (device.local) await nativeStore.cache(userId, device.local.epoch, data).catch(error => device.setError(String(error)))
    qc.setQueryData(['native-listening-session', userId, data.id], data)
    setParams({ sessao: String(data.id) }, { replace: true })
  }
  const start = useMutation({ networkMode: 'always', retry: false,
    mutationFn: () => startNative(slug, detail.data!.version, startKey), onSuccess: accept,
  })
  const cached = device.local?.sessions.find(item => item.id === sessionId && item.activity.slug === slug)
  const active = cached && cached.revision >= (session.data?.revision ?? -1) ? cached : session.data
  const commands = device.local?.commands.filter(item => item.sessionId === sessionId) ?? []
  const send = async (body: NativeResponse, draftId?: string) => {
    if (!active || !device.local) return
    setSaving(true); device.setError('')
    try { await nativeStore.enqueue(userId, device.local.epoch, active, body, draftId); await device.sync() }
    catch (error) { device.setError(String(error)) }
    finally { setSaving(false) }
  }
  const activity = active?.activity ?? detail.data
  const blocked = saving || !device.local || commands.some(item => item.blocked)
  return <section className="listening-page" aria-labelledby="native-title">
    <Link to="/listening">Voltar ao listening rápido</Link>
    <h1 id="native-title">{activity?.title ?? 'Prática de listening'}</h1>
    {invalidSession && <p role="alert">O endereço da sessão é inválido. <button type="button" onClick={() => setParams({})}>Voltar ao início da prática</button></p>}
    {activity?.preview && <p role="status">Prévia local para revisão: conteúdo A2 e áudio sintético ainda não aprovados para publicação.</p>}
    {(!online || offline) && <p role="status">Sem confirmação online. Respostas de uma sessão já aberta podem ficar pendentes neste dispositivo. Áudio exige conexão.</p>}
    {(detail.isError || session.isError) && !active && <p role="alert">Não foi possível abrir a atividade ou a sessão.
      <button type="button" onClick={() => { void detail.refetch(); if (sessionId > 0) void session.refetch() }}>Tentar novamente</button></p>}
    {!activity && detail.isPending && <p role="status">Carregando atividade…</p>}
    {sessionId > 0 && session.isPending && !active && <p role="status">Carregando sessão…</p>}
    {device.error && <p role="alert">{device.error} <button type="button" disabled={!online || offline || device.syncing} onClick={() => void device.sync()}>Tentar enviar novamente</button></p>}
    {activity && <>
      <p lang="en">{activity.instructions}</p>
      <p>A nota considera sua primeira resposta a cada questão. Revelar a resposta antes de tentar vale zero nessa questão. Repetições são identificadas.</p>
      {sessionId === 0 && !invalidSession && <button type="button" disabled={!online || offline || start.isPending}
        onClick={() => start.mutate()}>{start.isPending ? 'Iniciando…' : start.isError ? 'Tentar iniciar novamente' : 'Iniciar prática'}</button>}
      {start.isError && <p role="alert">Não foi possível confirmar o início. Tente novamente.</p>}
      {active && <>
        <NativeAudioPlayer key={`${active.id}:${activity.version}`} activity={activity} userId={userId} sessionId={active.id} />
        {activity.map_rows.length > 0 && <figure className="native-map">
          <table lang="en"><caption>Map · North ↑</caption><tbody>
            {activity.map_rows.map((row, index) => <tr key={index}>{row.map(cell => <td key={cell}>{cell}</td>)}</tr>)}
          </tbody></table>
          <figcaption lang="en">{activity.map_description}</figcaption>
        </figure>}
        <p role="status">{active.completed ? 'Prática concluída. ' : ''}Primeiras respostas: {active.score} de {active.total}.
          {active.support_revealed && ' Transcrição revelada: prática com apoio textual.'}</p>
        <p role="status">{commands.length ? `${commands.length} resposta(s) pendente(s) de envio.` : 'Respostas confirmadas na conta.'}</p>
        {(saving || device.syncing) && <p role="status">Confirmando resposta…</p>}
        {commands.filter(item => item.blocked).map(item => <div role="alert" key={item.id}>
          <p>Resposta preservada: {item.status === 409 ? 'a sessão mudou em outra aba' : 'a atividade ou resposta precisa ser conferida'}. Questão: {item.body.question_id ?? 'apoio textual'}.</p>
          <p>Seleção pendente: {item.body.selected_ids?.map(id => activity.questions.find(q => q.id === item.body.question_id)?.options.find(option => option.id === id)?.label ?? id).join(', ') || 'revelação solicitada'}.</p>
          <button type="button" disabled={!online || offline || saving} onClick={() => {
            setSaving(true); void resolveNative(userId, device.local!.epoch, item).catch(error => device.setError(String(error))).finally(() => setSaving(false))
          }}>Enviar como nova tentativa</button>{' '}
          <button type="button" onClick={() => { if (window.confirm('Descartar somente esta resposta pendente?')) void nativeStore.remove(userId, device.local!.epoch, item.id).catch(error => device.setError(String(error))) }}>Descartar pendência</button>
        </div>)}
        <label><input type="checkbox" checked={onlyErrors} onChange={event => setOnlyErrors(event.target.checked)} />Revisar somente erros e respostas reveladas</label>
        {onlyErrors && !active.feedback.some(item => item.first_response && !item.correct) && <p>Nenhum erro confirmado nesta sessão.</p>}
        {activity.questions.map((question, index) => (!onlyErrors || active.feedback.some(item => item.question_id === question.id && item.first_response && !item.correct)) && <Question key={`${active.id}:${question.id}`} index={index}
          question={question} session={active} disabled={blocked || commands.some(item => item.body.question_id === question.id)} onSend={send}
          userId={userId} epoch={device.local?.epoch ?? 0} online={online && !offline}
          drafts={device.local?.drafts.filter(item => item.sessionId === active.id && item.version === active.activity.version && item.questionId === question.id) ?? []}
          onError={device.setError} />)}
        {!active.support_revealed
          ? <button type="button" disabled={blocked || !online || offline || commands.some(item => item.body.kind === 'transcript')} onClick={() => void send({ kind: 'transcript', question_id: null,
            selected_ids: [], expected_revision: active.revision, operation_key: crypto.randomUUID() })}>Revelar transcrição como apoio</button>
          : <section aria-label="Transcrição revelada"><h2>Transcrição · apoio textual</h2><p lang="en" className="native-transcript">{active.transcript}</p></section>}
      </>}
    </>}
  </section>
}

function Question({ question, index, session, disabled, onSend, userId, epoch, drafts, onError, online }: {
  question: NativeSession['activity']['questions'][number]; index: number; session: NativeSession
  disabled: boolean; onSend: (body: NativeResponse, draftId?: string) => Promise<void>
  userId: number; epoch: number; drafts: NativeDraft[]; onError: (message: string) => void; online: boolean
}) {
  const [selected, setSelected] = useState<string[]>([])
  const [draftSaved, setDraftSaved] = useState(false)
  const [editorId] = useState(() => crypto.randomUUID())
  const draftId = useRef<string | undefined>(undefined)
  const touched = useRef(false)
  const writing = useRef(Promise.resolve())
  const submitting = useRef(false)
  const results = session.feedback.filter(item => item.question_id === question.id)
  const latest = results.at(-1)
  useEffect(() => {
    if (touched.current) return
    const draft = drafts.at(-1)
    draftId.current = draft?.id
    setSelected(draft?.selected ?? latest?.selected_ids ?? EMPTY_IDS)
    setDraftSaved(Boolean(draft))
  }, [drafts, latest])
  const change = (ids: string[]) => {
    touched.current = true; setSelected(ids); setDraftSaved(false)
    writing.current = writing.current.then(async () => {
      const saved = await nativeStore.draft(userId, epoch, session, question.id, ids, draftId.current, editorId)
      draftId.current = saved.id; setDraftSaved(true)
    }).catch(error => { onError(String(error)) })
  }
  const description = `native-${question.id}-help`
  const submit = async (kind: 'answer' | 'reveal') => {
    if (submitting.current) return
    submitting.current = true
    try {
      await writing.current
      await onSend({ kind, question_id: question.id, selected_ids: kind === 'answer' ? selected : [], expected_revision: session.revision, operation_key: crypto.randomUUID() }, draftId.current)
      setDraftSaved(false)
    } finally { submitting.current = false }
  }
  return <section className="listening-card" aria-labelledby={`native-${question.id}-title`}>
    <h2 id={`native-${question.id}-title`} lang="en">{index + 1}. {question.prompt}</h2>
    <p id={description}>Selecione {question.selection_count === 2 ? 'exatamente duas opções' : 'uma opção'}.</p>
    <SelectionInput name={`native-${question.id}`} legend="Sua resposta" options={question.options}
      selected={selected} multiple={question.kind === 'multi_select'} disabled={disabled}
      description={description} onChange={change} />
    {draftSaved && <p>Rascunho salvo neste dispositivo.</p>}
    {drafts.length > 1 && <details><summary>Rascunhos de outras edições ({drafts.length})</summary>{drafts.map(draft => <p key={draft.id}>
      {draft.selected.map(id => question.options.find(option => option.id === id)?.label ?? id).join(', ')}{' '}
      <button type="button" onClick={() => { touched.current = true; draftId.current = draft.id; setSelected(draft.selected); setDraftSaved(true) }}>Usar este rascunho</button>
    </p>)}</details>}
    <button type="button" disabled={disabled || selected.length !== question.selection_count} onClick={() => void submit('answer')}>
      {results.length ? 'Responder novamente' : 'Confirmar resposta'}</button>{' '}
    {!latest && <button type="button" disabled={disabled || !online} onClick={() => void submit('reveal')}>Revelar resposta</button>}
    {latest && <div role="status">
      <p>{latest.kind === 'reveal' ? 'Resposta revelada.' : latest.correct ? 'Resposta correta.' : 'Resposta incorreta.'}
        {latest.first_response ? ' Primeira resposta registrada.' : ' Repetição: a nota inicial foi mantida.'}</p>
      <p>Resposta: {question.options.filter(option => latest.answer_ids.includes(option.id)).map(option => option.label).join(' + ')}.</p>
      <p>{latest.explanation}</p>
    </div>}
  </section>
}
