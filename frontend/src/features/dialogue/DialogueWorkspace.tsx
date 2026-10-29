import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type LessonDetail } from '../../api/client'
import { invalidateStudy } from '../../api/invalidateStudy'
import { READ_POLICY } from '../../api/readPolicy'
import { AssistQuota } from '../assist/AssistQuota'
import { VoiceRecorder } from '../speaking/voiceRecorder'
import { DialogueSession } from './dialogueSession'
import { dialogueTransport, type DialogueTransport, type Mode } from './dialogueTransport'
import { DialogueTurnView } from './DialogueTurnView'
import { PartnerSpeech } from './partnerSpeech'
import './dialogue.css'

export default function DialogueWorkspace({ lesson, userId, transport = dialogueTransport }: {
  lesson: LessonDetail; userId: number; transport?: DialogueTransport
}) {
  const engine = useMemo(() => new DialogueSession(userId, transport), [userId, transport])
  const state = useSyncExternalStore(engine.subscribe, engine.snapshot)
  const queryClient = useQueryClient()
  const [mode, setMode] = useState<Mode>('script')
  const [speaker, setSpeaker] = useState('')
  const [text, setText] = useState('')
  const [consent, setConsent] = useState(false)
  const [recording, setRecording] = useState<{ blob: Blob; duration: number } | null>(null)
  const [message, setMessage] = useState('')
  const [rate, setRate] = useState(0.85)
  const [online, setOnline] = useState(navigator.onLine)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const input = useRef<HTMLTextAreaElement>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const lastPosition = useRef(0)
  const focusAfterTurn = useRef(false)
  const microphoneStarted = useRef(false)
  const voices = useMemo(() => [...new Set(lesson.media.flatMap((media) => media.cues.map((cue) => cue.speaker).filter((name): name is string => Boolean(name))))], [lesson])
  const speech = useMemo(() => new PartnerSpeech(() => engine.speaking(false)), [engine])
  const recorder = useMemo(() => new VoiceRecorder({
    started: () => { microphoneStarted.current = true; engine.listening(true) },
    finished: (blob, duration) => { microphoneStarted.current = false; engine.listening(false); setRecording({ blob, duration }); setConsent(false) },
    failed: (reason) => { microphoneStarted.current = false; engine.listening(false); setMessage(`${reason} Você pode continuar por texto.`) },
  }), [engine])
  const status = useQuery({
    queryKey: ['dialogue-status', userId],
    queryFn: async ({ signal }) => {
      const { data } = await api.GET('/api/speaking/dialogues/status', { signal })
      if (!data) throw new Error('Não foi possível consultar a cota.')
      return data
    }, ...READ_POLICY, staleTime: 30_000,
  })
  const policy = useQuery({
    queryKey: ['speaking-policy'],
    queryFn: async ({ signal }) => {
      const { data } = await api.GET('/api/speaking/policy', { signal })
      if (!data) throw new Error('Não foi possível consultar os limites de gravação.')
      return data
    }, ...READ_POLICY, enabled: Boolean(status.data?.audio_enabled),
  })
  const recordingUrl = useMemo(() => recording ? URL.createObjectURL(recording.blob) : null, [recording])
  useEffect(() => () => { if (recordingUrl) URL.revokeObjectURL(recordingUrl) }, [recordingUrl])
  useEffect(() => {
    const update = () => setOnline(navigator.onLine)
    window.addEventListener('online', update); window.addEventListener('offline', update)
    heading.current?.focus()
    return () => {
      window.removeEventListener('online', update); window.removeEventListener('offline', update)
      engine.dispose(); recorder.cancel(); speech.cancel()
    }
  }, [engine, recorder, speech])
  useEffect(() => {
    const position = Math.max(0, ...state.dialogue?.turns.filter((turn) => turn.state !== 'pending').map((turn) => turn.position) ?? [])
    if (position > lastPosition.current) {
      lastPosition.current = position
      focusAfterTurn.current = true
      setText(''); setRecording(null); setConsent(false)
      void invalidateStudy(queryClient, 'dialogueChange')
    }
    if (!state.dialogue) { lastPosition.current = 0; focusAfterTurn.current = false }
  }, [state.dialogue, queryClient, userId])

  const guided = state.dialogue?.mode === 'guided'
  const busy = ['uploading', 'waiting', 'listening', 'partner_speaking'].includes(state.phase)
  const blocked = busy || state.pendingInput || state.awaiting || !online || !status.data?.enabled
    || (guided && !status.data.guided_enabled)
  const finished = state.dialogue?.turns_remaining === 0
  const audioAllowed = guided && status.data?.audio_enabled && policy.data
  const recordingInvalid = Boolean(recording && policy.data && (recording.blob.size > policy.data.max_bytes
    || recording.duration > policy.data.max_duration_ms || !policy.data.mime_types.includes(recording.blob.type.split(';')[0]!)))
  useEffect(() => {
    // Após áudio, o render seguinte libera o textarea ao remover a gravação.
    if (focusAfterTurn.current && input.current && !input.current.disabled) {
      focusAfterTurn.current = false
      input.current.focus()
    }
  }, [state.dialogue, recording, blocked])
  const say = (copy: string) => {
    if (speech.play(copy, rate)) engine.speaking(true)
    else setMessage('Não há voz local em inglês americano disponível. A resposta permanece em texto.')
  }
  const clearRecording = () => { recorder.cancel(); setRecording(null); setConsent(false); engine.listening(false) }
  const startRecording = () => {
    if (!policy.data || blocked) return
    setMessage(''); setConsent(false); microphoneStarted.current = false
    engine.listening(true)
    void recorder.start(policy.data.recording_target_ms, policy.data.mime_types)
  }
  const remove = async () => {
    recorder.cancel(); speech.cancel()
    await engine.remove()
    setConfirmDelete(false)
    if (!engine.snapshot().dialogue) { setText(''); setRecording(null); setConsent(false); heading.current?.focus() }
    void invalidateStudy(queryClient, 'dialogueChange')
  }

  return <section className="study-section dialogue-workspace" aria-labelledby="dialogue-heading">
    <h2 id="dialogue-heading" tabIndex={-1} ref={heading}>Parceiro de conversa · Aula {lesson.number}</h2>
    <p>Pratique o vocabulário desta aula. As verificações de texto não avaliam pronúncia nem fluência.</p>
    {!online && <p role="alert">Você está offline. O rascunho fica nesta tela; volte à conexão para enviar.</p>}
    {status.isError && <p role="alert">Não foi possível consultar a cota. <button onClick={() => void status.refetch()}>Consultar novamente</button></p>}
    {status.data && <AssistQuota status={status.data} modality="conversation" />}
    {!state.dialogue ? <fieldset disabled={blocked}>
      <legend>Começar uma conversa</legend>
      <label>Modo<select value={mode} onChange={(event) => setMode(event.target.value as Mode)}>
        <option value="script">Roteiro por texto</option>
        <option value="guided" disabled={!status.data?.guided_enabled}>Guiado · automatizado, em avaliação</option>
      </select></label>
      <label>Personagem<select value={speaker} onChange={(event) => setSpeaker(event.target.value)}>
        <option value="">Personagem padrão da aula</option>
        {voices.map((name) => <option key={name} value={name}>{name}</option>)}
      </select></label>
      <p>{mode === 'script' ? 'As respostas vêm do roteiro. Nenhum provedor é necessário.'
        : `O texto e, se você autorizar, o áudio serão processados automaticamente. Retenção de ${status.data?.retention_days ?? 30} dias. Evite informações pessoais.`}</p>
      <button className="btn" disabled={mode === 'guided' && !status.data?.guided_enabled} onClick={() => void engine.open(lesson.id, mode, speaker || null)}>Iniciar conversa</button>
    </fieldset> : <>
      {guided && !status.data?.guided_enabled && <p role="alert">O modo Guiado está indisponível. Inicie uma nova conversa no Roteiro para continuar por texto.</p>}
      <p>Modo {guided ? 'Guiado' : 'Roteiro'} · {state.dialogue.turns_remaining} turnos restantes de {state.dialogue.turn_limit}.</p>
      <label>Velocidade da voz<select value={rate} onChange={(event) => setRate(Number(event.target.value))}>
        <option value={0.65}>Lenta</option><option value={0.85}>Moderada</option><option value={1}>Normal</option>
      </select></label>
      <ol className="dialogue-turns">{state.dialogue.turns.map((turn) => <DialogueTurnView key={turn.position} turn={turn} guided={guided}
        disabled={blocked} onRate={(rating) => void engine.rate(turn.position, rating)} onSpeak={say} />)}</ol>
      {state.phase === 'partner_speaking' && <button onClick={() => { speech.cancel(); engine.speaking(false); input.current?.focus() }}>Parar voz</button>}
      {finished ? <p role="status">Conversa concluída. Você chegou ao limite de turnos.</p> : <>
        <label>Sua resposta em inglês<textarea ref={input} lang="en" maxLength={2000} value={text}
          disabled={blocked || Boolean(recording)} onChange={(event) => setText(event.target.value)} /></label>
        <p>{text.length}/2000 caracteres. Procure usar de três a sessenta palavras.</p>
        <button className="btn" disabled={blocked || Boolean(recording) || !text.trim()} onClick={() => void engine.sendText(text)}>Enviar texto</button>
        {audioAllowed && <div className="dialogue-recording">
          <p>Grave até {policy.data!.recording_target_ms / 1000} segundos. Envio limitado a {policy.data!.max_bytes.toLocaleString('pt-BR')} bytes.</p>
          {state.phase === 'listening' ? <button onClick={() => {
            if (microphoneStarted.current) recorder.stop()
            else { recorder.cancel(); engine.listening(false) }
          }}>Parar gravação</button>
            : <button disabled={blocked || Boolean(recording)} onClick={startRecording}>Gravar resposta</button>}
          {recording && recordingUrl && <>
            <audio controls src={recordingUrl} aria-label="Ouvir gravação local" />
            <a href={recordingUrl} download="minha-resposta">Baixar gravação</a>
            <label><input type="checkbox" checked={consent} disabled={blocked}
              onChange={(event) => setConsent(event.target.checked)} />Concordo em salvar e transcrever esta gravação para responder à conversa.</label>
            {recordingInvalid && <p role="alert">Gravação fora dos limites. Baixe o áudio ou grave um trecho menor.</p>}
            <button disabled={blocked || !consent || recordingInvalid} onClick={() => void engine.sendAudio(recording.blob, recording.duration, consent, policy.data!)}>Enviar áudio</button>
            <button disabled={blocked} onClick={clearRecording}>Descartar gravação local</button>
            <p>A gravação fica nesta tela até o envio. Baixe antes de sair para guardar uma cópia.</p>
          </>}
        </div>}
        {guided && policy.isError && <p role="alert">Limites de áudio indisponíveis. Continue por texto ou <button onClick={() => void policy.refetch()}>consulte os limites</button>.</p>}
      </>}
      <button disabled={busy || state.pendingInput || state.awaiting} onClick={() => {
        engine.leave(); setMode('script'); setText(''); clearRecording(); heading.current?.focus()
      }}>Nova conversa no Roteiro</button>
      <button disabled={state.phase === 'uploading'} onClick={() => setConfirmDelete(true)}>Excluir conversa</button>
      {confirmDelete && <div role="group" aria-label="Confirmar exclusão da conversa">
        <p>Excluir a conversa, seus turnos e as revisões derivadas? Gravações seguem a política de retenção da conta; custos já consumidos permanecem.</p>
        <button onClick={() => void remove()}>Confirmar exclusão</button><button onClick={() => setConfirmDelete(false)}>Cancelar exclusão</button>
      </div>}
    </>}
    <p role="status" aria-live="polite" aria-atomic="true">{state.phase === 'uploading' ? 'Enviando…' : state.phase === 'waiting' ? 'Aguardando resposta…'
      : state.phase === 'listening' ? 'Gravando…' : state.phase === 'partner_speaking' ? 'Reproduzindo resposta…'
        : state.dialogue?.turns.at(-1)?.partner_text ? `Resposta do parceiro: ${state.dialogue.turns.at(-1)?.partner_text}` : ''}</p>
    {state.message && <p role={state.phase === 'error' ? 'alert' : 'status'}>{state.message}</p>}
    {state.phase === 'error' && state.dialogue && <button disabled={!online} onClick={() => void engine.retry()}>Consultar ou reenviar entrada original</button>}
    {message && <p role="status">{message}</p>}
  </section>
}
