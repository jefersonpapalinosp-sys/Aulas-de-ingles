import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  api,
  authenticatedFetch,
  type LessonMedia,
  type SpeakingAttempt,
} from '../../api/client'
import { useAssistStatus } from '../../api/assist'
import { AssistQuota } from '../assist/AssistQuota'
import { formatAudioTime } from '../media/LessonAudioPlayer'
import { readLocal, writeLocal } from '../../storage/local'
import { sessionSnapshot } from '../../api/session'
import { recordingTypes, VoiceRecorder } from './voiceRecorder'
import { clearVoiceDraft, retainVoiceDraft, takeVoiceDraft } from './voiceDraft'

type RecordingStatus = 'idle' | 'requesting' | 'recording' | 'ready' | 'error'
type SelfRating = 'repeat' | 'almost' | 'confident'

function ratingKey(
  userId: number,
  courseSlug: string,
  lessonNumber: number,
  cueId: number,
): string {
  return `aulas-ingles:shadowing-rating:v2:${userId}:${courseSlug}:${lessonNumber}:${cueId}`
}

export function ShadowingPractice({
  courseSlug,
  media,
  userId,
  lessonNumber,
}: {
  courseSlug: string
  media: LessonMedia
  userId: number
  lessonNumber: number
}) {
  const queryClient = useQueryClient()
  const firstCue = media.cues[0]
  const [cueId, setCueId] = useState(firstCue?.id ?? 0)
  const [status, setStatus] = useState<RecordingStatus>('idle')
  const [recordingUrl, setRecordingUrl] = useState<string | null>(null)
  const [recordingBlob, setRecordingBlob] = useState<Blob | null>(null)
  const [recordingDuration, setRecordingDuration] = useState(0)
  const [message, setMessage] = useState('')
  const [storageWarning, setStorageWarning] = useState('')
  const [modelPlaying, setModelPlaying] = useState(false)
  const [rating, setRating] = useState<SelfRating | null>(null)
  const [consent, setConsent] = useState(false)
  const [saving, setSaving] = useState(false)
  const [savedCurrent, setSavedCurrent] = useState(false)
  const [savedAudioUrl, setSavedAudioUrl] = useState<string | null>(null)
  const [playingAttemptId, setPlayingAttemptId] = useState<number | null>(null)
  const modelRef = useRef<HTMLAudioElement>(null)
  const uploadRef = useRef<{ attemptId: number | null; controller: AbortController | null }>({ attemptId: null, controller: null })
  const recoveredRef = useRef<ReturnType<typeof takeVoiceDraft>>(null)
  const [pendingAttempt, setPendingAttempt] = useState(false)
  const recorder = useMemo(() => new VoiceRecorder({
    started: () => { setStatus('recording'); setMessage('Gravando… fale a frase e pare quando terminar.') },
    finished: (blob, duration) => {
      setRecordingBlob(blob)
      setRecordingDuration(duration)
      setRecordingUrl(URL.createObjectURL(blob))
      setStatus('ready')
      setMessage('Gravação pronta. Compare sua voz com o modelo.')
    },
    failed: (text) => { setStatus('error'); setMessage(text) },
  }), [])
  const cue = media.cues.find((item) => item.id === cueId) ?? firstCue
  const draftKey = `${userId}:${courseSlug}:${lessonNumber}:${cue?.id}`
  const historyKey = useMemo(
    () => ['speaking-attempts', userId, courseSlug, lessonNumber] as const,
    [courseSlug, lessonNumber, userId],
  )
  const historyQuery = useQuery({
    queryKey: historyKey,
    queryFn: async () => {
      const { data } = await api.GET('/api/speaking/attempts', {
        params: { query: { lesson: lessonNumber, course: courseSlug } },
      })
      if (!data) throw new Error('Não foi possível carregar as gravações.')
      return data
    },
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.some((attempt) =>
        ['queued', 'processing'].includes(attempt.transcription?.status ?? ''),
      )
        ? 1500
        : false,
  })
  const assistStatus = useAssistStatus(userId)
  const policyQuery = useQuery({
    queryKey: ['speaking-policy'],
    queryFn: async () => {
      const { data } = await api.GET('/api/speaking/policy')
      if (!data) throw new Error('Não foi possível confirmar os limites de envio.')
      return data
    },
    retry: false,
  })
  const policy = policyQuery.data
  // Margem para o fechamento do codec; o servidor mede e limita a duração real.
  const maxDuration = policy?.recording_target_ms ?? 29_000
  const supported =
    typeof navigator !== 'undefined' &&
    typeof navigator.mediaDevices?.getUserMedia === 'function' &&
    typeof MediaRecorder !== 'undefined' && typeof MediaRecorder.isTypeSupported === 'function'

  useEffect(() => {
    recorder.cancel()
    uploadRef.current.controller?.abort()
    uploadRef.current = { attemptId: null, controller: null }
    setPendingAttempt(false)
    setSaving(false)
    if (!cue) return
    if (modelRef.current && !modelRef.current.paused) modelRef.current.pause()
    const key = ratingKey(userId, courseSlug, lessonNumber, cue.id)
    const local = readLocal(key)
    let saved = local.ok ? local.value : null
    let warning = local.ok ? '' : local.error
    if (local.ok && !saved && courseSlug === 'voa-level-1') {
      const legacy = readLocal(
        `aulas-ingles:shadowing-rating:v1:${userId}:${lessonNumber}:${cue.id}`,
      )
      saved = legacy.ok ? legacy.value : null
      if (!legacy.ok) warning = legacy.error
      if (saved) {
        const result = writeLocal(key, saved)
        if (!result.ok) warning = result.error
      }
    }
    setStorageWarning(warning)
    setRating(
      saved === 'repeat' || saved === 'almost' || saved === 'confident' ? saved : null,
    )
    setRecordingUrl(null)
    setRecordingBlob(null)
    setRecordingDuration(0)
    setConsent(false)
    setSavedCurrent(false)
    setStatus('idle')
    setMessage('')
    const restored = takeVoiceDraft(draftKey) ?? (recoveredRef.current?.key === draftKey ? recoveredRef.current : null)
    recoveredRef.current = restored
    const restoredUrl = restored ? URL.createObjectURL(restored.blob) : null
    if (restored) {
      setRecordingBlob(restored.blob)
      setRecordingDuration(restored.duration)
      setRecordingUrl(restoredUrl)
      uploadRef.current.attemptId = restored.attemptId
      setPendingAttempt(restored.attemptId !== null)
      setStatus('ready')
      setMessage('Gravação recuperada nesta aba. Confira e autorize o envio novamente.')
    }
    return () => {
      recorder.cancel()
      uploadRef.current.controller?.abort()
      // StrictMode pode limpar este efeito antes de o estado publicar a primeira URL.
      if (restoredUrl) URL.revokeObjectURL(restoredUrl)
    }
  }, [courseSlug, cue, lessonNumber, userId, recorder, draftKey])

  useEffect(
    () => () => {
      if (recordingUrl && typeof URL.revokeObjectURL === 'function') {
        URL.revokeObjectURL(recordingUrl)
      }
    },
    [recordingUrl],
  )

  useEffect(
    () => () => {
      if (savedAudioUrl && typeof URL.revokeObjectURL === 'function') {
        URL.revokeObjectURL(savedAudioUrl)
      }
    },
    [savedAudioUrl],
  )

  if (!cue) return null

  async function playModel() {
    const audio = modelRef.current
    if (!audio || !cue) return
    try {
      audio.currentTime = cue.start_seconds
      await audio.play()
      setModelPlaying(true)
      setMessage('Ouça o ritmo e repita logo depois.')
    } catch {
      setMessage('Não foi possível reproduzir o modelo. Tente usar o player da etapa Assistir.')
    }
  }

  async function startRecording() {
    if (!supported || saving) return
    recoveredRef.current = null
    setStatus('requesting')
    setMessage('Solicitando acesso ao microfone…')
    setRecordingUrl(null)
    setRecordingBlob(null)
    setConsent(false)
    setSavedCurrent(false)
    uploadRef.current = { attemptId: null, controller: null }
    setPendingAttempt(false)
    await recorder.start(maxDuration, policy?.mime_types ?? recordingTypes.map((type) => type.split(';')[0]!))
  }

  function saveRating(value: SelfRating) {
    if (!cue) return
    setRating(value)
    const result = writeLocal(ratingKey(userId, courseSlug, lessonNumber, cue.id), value)
    setStorageWarning(result.ok ? '' : result.error)
    setMessage(result.ok ? 'Autoavaliação salva neste navegador.' : 'Autoavaliação apenas nesta tela; não foi salva neste navegador.')
  }

  function discardLocal() {
    recoveredRef.current = null
    clearVoiceDraft(draftKey)
    recorder.cancel()
    uploadRef.current.controller?.abort()
    uploadRef.current = { attemptId: null, controller: null }
    setPendingAttempt(false)
    setRecordingUrl(null)
    setRecordingBlob(null)
    setRecordingDuration(0)
    setConsent(false)
    setSavedCurrent(false)
    setStatus('idle')
    setMessage('Gravação local descartada.')
  }

  async function saveRecording() {
    if (!cue || !recordingBlob || !consent || savedCurrent || !policy || saving || uploadRef.current.controller) return
    const session = sessionSnapshot()
    if (session.usuarioId !== userId || !session.token || session.perfilNaoConfirmado) {
      setMessage('Confirme a sessão da mesma conta para tentar novamente. O áudio continua nesta tela.')
      return
    }
    const uploadState = uploadRef.current
    const recovery = { key: draftKey, blob: recordingBlob, duration: recordingDuration, attemptId: uploadState.attemptId }
    retainVoiceDraft(recovery)
    const controller = new AbortController()
    uploadState.controller = controller
    const current = () => !controller.signal.aborted && uploadRef.current === uploadState
    const validAccount = () => current() && sessionSnapshot().geracao === session.geracao && sessionSnapshot().usuarioId === userId
    setSaving(true)
    setMessage('Salvando gravação com segurança…')
    try {
      if (uploadState.attemptId === null) {
        const { data: attempt, response } = await api.POST('/api/speaking/attempts', {
          body: { cue_id: cue.id, duration_ms: recordingDuration, self_rating: rating, consent: true },
          signal: controller.signal,
        })
        if (!validAccount()) throw new Error('A sessão mudou. Confirme a mesma conta antes de reenviar.')
        if (!attempt) throw new Error(uploadError(response?.status))
        uploadState.attemptId = attempt.id
        recovery.attemptId = attempt.id
        setPendingAttempt(true)
      }
      const upload = await authenticatedFetch(`/api/speaking/attempts/${uploadState.attemptId}/audio`, {
        method: 'PUT',
        headers: { 'Content-Type': recordingBlob.type },
        body: recordingBlob,
        signal: controller.signal,
      })
      if (!validAccount()) throw new Error('A sessão mudou. Confirme a mesma conta antes de reenviar.')
      if (!upload.ok) throw new Error(uploadError(upload.status))
      setSavedCurrent(true)
      setConsent(false)
      setMessage('Gravação salva na sua conta. Você pode ouvi-la ou excluí-la abaixo.')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: historyKey }),
        queryClient.invalidateQueries({ queryKey: ['course-completion', courseSlug] }),
      ])
    } catch (error) {
      // Falha de rede pode ser só perda da resposta: não apagar uma gravação confirmada.
      if (current()) setMessage(`${error instanceof Error && error.message !== 'Failed to fetch' ? error.message : 'Falha de conexão. Tente novamente.'} O áudio continua nesta tela; você pode baixá-lo.`)
    } finally {
      if (sessionSnapshot().usuarioId !== null) clearVoiceDraft(draftKey, recovery)
      uploadState.controller = null
      if (current()) setSaving(false)
    }
  }

  async function playSaved(attempt: SpeakingAttempt) {
    setMessage('Carregando gravação salva…')
    try {
      const response = await authenticatedFetch(`/api/speaking/attempts/${attempt.id}/audio`)
      if (!response.ok) throw new Error('Falha ao carregar o áudio.')
      const blob = await response.blob()
      setSavedAudioUrl(URL.createObjectURL(blob))
      setPlayingAttemptId(attempt.id)
      setMessage('Gravação salva carregada.')
    } catch {
      setMessage('Não foi possível carregar essa gravação.')
    }
  }

  async function deleteSaved(attemptId: number) {
    const { response } = await api.DELETE('/api/speaking/attempts/{attempt_id}', {
      params: { path: { attempt_id: attemptId } },
    })
    if (!response.ok) {
      setMessage('Não foi possível excluir essa gravação.')
      return
    }
    if (playingAttemptId === attemptId) {
      setSavedAudioUrl(null)
      setPlayingAttemptId(null)
    }
    setMessage('Gravação excluída da sua conta.')
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: historyKey }),
      queryClient.invalidateQueries({ queryKey: ['course-completion', courseSlug] }),
      queryClient.invalidateQueries({ queryKey: ['assist-status', userId] }),
    ])
  }

  async function requestTranscription(attemptId: number) {
    setMessage('Solicitando transcrição automatizada…')
    const { data, response } = await api.POST(
      '/api/speaking/attempts/{attempt_id}/transcription',
      { params: { path: { attempt_id: attemptId } } },
    )
    if (!data) {
      setMessage(
        response?.status === 429
          ? 'A cota diária de análises assistidas foi atingida.'
          : 'O provedor não está disponível. Sua gravação e autoavaliação continuam salvas.',
      )
      await queryClient.invalidateQueries({ queryKey: ['assist-status', userId] })
      return
    }
    setMessage('Transcrição solicitada. Este resultado será claramente marcado como automático.')
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: historyKey }),
      queryClient.invalidateQueries({ queryKey: ['assist-status', userId] }),
    ])
  }

  async function rateTranscription(jobId: number, rating: 'helpful' | 'not_helpful') {
    const { data } = await api.PUT('/api/speaking/transcriptions/{job_id}/rating', {
      params: { path: { job_id: jobId } },
      body: { rating },
    })
    if (!data) {
      setMessage('Não foi possível salvar sua avaliação da transcrição.')
      return
    }
    setMessage('Obrigado. Sua avaliação ajuda a decidir se o recurso pode ser liberado.')
    await queryClient.invalidateQueries({ queryKey: historyKey })
  }

  async function deleteTranscription(jobId: number) {
    const { response } = await api.DELETE('/api/speaking/transcriptions/{job_id}', {
      params: { path: { job_id: jobId } },
    })
    if (!response.ok) {
      setMessage('Não foi possível excluir a transcrição.')
      return
    }
    setMessage('Transcrição excluída. A gravação foi mantida.')
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: historyKey }),
      queryClient.invalidateQueries({ queryKey: ['assist-status', userId] }),
    ])
  }

  return (
    <section className="shadowing-card" aria-labelledby="shadowing-title">
      <p className="study-kicker">Speaking · shadowing</p>
      <h2 id="shadowing-title">Escute, repita e compare sua voz</h2>
      <p className="study-copy">
        Por padrão, a gravação fica somente nesta tela e é descartada ao sair. Ela só será
        enviada se você marcar o consentimento e escolher salvar na sua conta.
        Se a sessão expirar durante o envio, tente entrar na mesma conta e retornar
        a este trecho em até cinco minutos, sem fechar ou recarregar esta aba.
      </p>

      <label className="shadowing-select">
        Frase para praticar
        <select
          value={cue.id}
          disabled={saving || status === 'requesting' || status === 'recording'}
          onChange={(event) => setCueId(Number(event.target.value))}
        >
          {media.cues.map((item) => (
            <option key={item.id} value={item.id}>
              {formatAudioTime(item.start_seconds)} · {item.speaker} — {item.text_en}
            </option>
          ))}
        </select>
      </label>

      <blockquote lang="en">
        <strong>{cue.speaker}</strong>
        <span>{cue.text_en}</span>
      </blockquote>

      <audio
        ref={modelRef}
        src={media.source_url}
        preload="metadata"
        aria-hidden="true"
        onPause={() => setModelPlaying(false)}
        onTimeUpdate={(event) => {
          if (event.currentTarget.currentTime >= cue.end_seconds) event.currentTarget.pause()
        }}
      />

      <div className="shadowing-actions">
        <button type="button" className="btn ghost" onClick={() => void playModel()}>
          {modelPlaying ? 'Ouvindo modelo…' : '1. Ouvir modelo'}
        </button>
        {status === 'recording' ? (
          <button type="button" className="btn recording" onClick={() => recorder.stop()}>
            Parar gravação
          </button>
        ) : (
          <button
            type="button"
            className="btn"
            disabled={!supported || saving || status === 'requesting'}
            onClick={() => void startRecording()}
          >
            {status === 'requesting' ? 'Abrindo microfone…' : '2. Gravar minha voz'}
          </button>
        )}
      </div>

      {status === 'requesting' && <button type="button" onClick={discardLocal}>Cancelar acesso ao microfone</button>}
      <p>Gravação local: até {maxDuration / 1000} segundos. {policy ? `Envio: até ${policy.max_bytes.toLocaleString('pt-BR')} bytes e ${policy.max_duration_ms / 1000} segundos reais, somente áudio mono ou estéreo.` : 'Limite de envio ainda não confirmado.'}</p>
      {policyQuery.isError && <button type="button" onClick={() => void policyQuery.refetch()}>Consultar limites para enviar</button>}

      {!supported && (
        <p className="shadowing-warning" role="alert">
          Este navegador não oferece gravação de áudio. Você ainda pode ouvir o modelo e repetir
          em voz alta.
        </p>
      )}
      {storageWarning && <p role="alert" className="erro">{storageWarning}</p>}
      {message && (
        <p className="shadowing-status" role="status">
          {message}
        </p>
      )}

      {recordingUrl && (
        <div className="shadowing-result">
          <label>
            3. Ouvir minha gravação
            <audio controls src={recordingUrl} preload="metadata" />
          </label>
          <fieldset>
            <legend>4. Como foi sua tentativa?</legend>
            {(
              [
                ['repeat', 'Quero repetir'],
                ['almost', 'Quase lá'],
                ['confident', 'Confiante'],
              ] as const
            ).map(([value, label]) => (
              <button
                type="button"
                key={value}
                className={rating === value ? 'selected' : ''}
                aria-pressed={rating === value}
                disabled={saving || pendingAttempt}
                onClick={() => saveRating(value)}
              >
                {label}
              </button>
            ))}
          </fieldset>
          <label className="speaking-consent">
            <input
              type="checkbox"
              checked={consent}
              disabled={saving || savedCurrent}
              onChange={(event) => setConsent(event.target.checked)}
            />
            <span>
              Concordo em salvar esta gravação na minha conta. Posso excluí-la quando quiser.
            </span>
          </label>
          <div className="speaking-save-actions">
            <button
              type="button"
              className="btn"
              disabled={
                !recordingBlob ||
                !consent ||
                saving ||
                savedCurrent ||
                !policy || recordingBlob.size > policy.max_bytes ||
                !policy.mime_types.includes(recordingBlob.type.split(';')[0]!)
              }
              onClick={() => void saveRecording()}
            >
              {saving ? 'Salvando…' : savedCurrent ? 'Gravação salva' : 'Salvar na minha conta'}
            </button>
            <button type="button" className="btn ghost" disabled={saving} onClick={discardLocal}>
              Descartar gravação local
            </button>
          </div>
          <a href={recordingUrl} download="minha-gravacao">Baixar gravação local</a>
          {recordingBlob && !savedCurrent && <p role="note">
            Gravação local — envio não confirmado. Ela não entra na fila de exercícios.
            Envie ou baixe antes de fechar a aba para não perder esta tentativa.
          </p>}
          {recordingBlob && policy && recordingBlob.size > policy.max_bytes && (
            <p className="shadowing-warning" role="alert">
              O arquivo excede {policy.max_bytes.toLocaleString('pt-BR')} bytes. Baixe a gravação ou faça uma tentativa mais curta.
            </p>
          )}
          {recordingBlob && policy && !policy.mime_types.includes(recordingBlob.type.split(';')[0]!) && (
            <p role="alert">Este formato não pode ser enviado. Baixe a gravação ou use outro navegador.</p>
          )}
        </div>
      )}

      <div className="speaking-history">
        <h3>Gravações salvas nesta aula</h3>
        {assistStatus.data && !assistStatus.data.transcription_enabled && (
          <p>
            Transcrição automática está desativada. Ouvir, comparar e autoavaliar continuam
            disponíveis normalmente.
          </p>
        )}
        {assistStatus.data?.transcription_enabled && (
          <p className="assist-disclosure">
            Recurso experimental: a transcrição é automatizada, pode errar e expira em{' '}
            {assistStatus.data.retention_days} dias.
          </p>
        )}
        {assistStatus.data?.transcription_enabled && <AssistQuota status={assistStatus.data} />}
        {historyQuery.isPending && <p>Carregando histórico…</p>}
        {historyQuery.isError && <p>Não foi possível carregar o histórico.</p>}
        {historyQuery.data?.length === 0 && <p>Nenhuma gravação salva.</p>}
        {historyQuery.data && historyQuery.data.length > 0 && (
          <ul>
            {historyQuery.data.map((attempt) => (
              <li key={attempt.id}>
                <div>
                  {attempt.cue_text ? (
                    <strong lang="en">{attempt.cue_text}</strong>
                  ) : (
                    <strong>Texto original indisponível</strong>
                  )}
                  <small>
                    {new Intl.DateTimeFormat('pt-BR', {
                      dateStyle: 'short',
                      timeStyle: 'short',
                    }).format(new Date(attempt.created_at))}
                    {attempt.self_rating ? ` · ${ratingLabel(attempt.self_rating)}` : ''}
                  </small>
                </div>
                <button type="button" disabled={['missing', 'changed'].includes(attempt.integrity_state ?? '')} onClick={() => void playSaved(attempt)}>Ouvir</button>
                {['missing', 'changed'].includes(attempt.integrity_state ?? '') && (
                  <p role="status">Arquivo ausente ou alterado. O histórico foi preservado; grave uma nova tentativa ou solicite restauração de uma cópia conferida.</p>
                )}
                {attempt.historical_content_status === 'unavailable' && (
                  <p role="status">
                    Sem texto original: ouça o áudio, sem comparação automática.
                  </p>
                )}
                <button type="button" onClick={() => void deleteSaved(attempt.id)}>Excluir</button>
                {assistStatus.data?.transcription_enabled && !attempt.transcription && attempt.historical_content_status === 'available' && !['missing', 'changed'].includes(attempt.integrity_state ?? '') && (
                  <button
                    type="button"
                    className="transcription-request"
                    onClick={() => void requestTranscription(attempt.id)}
                  >
                    Transcrever (experimental)
                  </button>
                )}
                {attempt.transcription && (
                  <div className={`transcription-result ${attempt.transcription.status}`}>
                    <p className="assist-label">Automatizado · somente avaliação</p>
                    {attempt.transcription.status === 'queued' && (
                      <p role="status">
                        {attempt.transcription.attempt_count === 0
                          ? 'Transcrição aguardando processamento…'
                          : `O provedor não respondeu. Nova tentativa será feita automaticamente (${attempt.transcription.attempt_count} de ${attempt.transcription.max_attempts} realizadas).`}
                      </p>
                    )}
                    {attempt.transcription.status === 'processing' && (
                      <p role="status">
                        Transcrição em processamento · tentativa{' '}
                        {attempt.transcription.attempt_count} de {attempt.transcription.max_attempts}.
                      </p>
                    )}
                    {attempt.transcription.status === 'failed' && (
                      <p role="alert">
                        A transcrição falhou após {attempt.transcription.attempt_count}{' '}
                        {attempt.transcription.attempt_count === 1 ? 'tentativa' : 'tentativas'}.
                        A gravação e sua autoavaliação não foram perdidas.
                      </p>
                    )}
                    {attempt.transcription.status === 'completed' && (
                      <>
                        <p className="transcription-copy" lang="en">
                          {attempt.transcription.words.map((word, index) => (
                            <span
                              className={word.confidence < 0.75 ? 'low-confidence' : ''}
                              title={`${Math.round(word.confidence * 100)}% de confiança`}
                              key={`${word.text}-${index}`}
                            >
                              {word.text}{' '}
                            </span>
                          ))}
                        </p>
                        <p className="transcription-metrics">
                          Confiança média{' '}
                          {Math.round((attempt.transcription.mean_confidence ?? 0) * 100)}% ·
                          semelhança com a frase{' '}
                          {Math.round((attempt.transcription.similarity_score ?? 0) * 100)}%
                        </p>
                        {attempt.transcription.low_confidence && (
                          <p className="assist-warning" role="alert">
                            Baixa confiança: ouça sua gravação e não trate esta transcrição como
                            correção definitiva.
                          </p>
                        )}
                        <div className="assist-rating" aria-label="Avaliar transcrição automática">
                          <span>Este resultado ajudou?</span>
                          <button
                            type="button"
                            aria-pressed={attempt.transcription.human_rating === 'helpful'}
                            onClick={() => void rateTranscription(attempt.transcription!.id, 'helpful')}
                          >
                            Sim
                          </button>
                          <button
                            type="button"
                            aria-pressed={attempt.transcription.human_rating === 'not_helpful'}
                            onClick={() =>
                              void rateTranscription(attempt.transcription!.id, 'not_helpful')
                            }
                          >
                            Não
                          </button>
                        </div>
                      </>
                    )}
                    <button
                      type="button"
                      className="assist-delete"
                      onClick={() => void deleteTranscription(attempt.transcription!.id)}
                    >
                      Excluir transcrição
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
        {savedAudioUrl && playingAttemptId !== null && (
          <audio
            aria-label="Reprodução da gravação salva"
            controls
            autoPlay
            src={savedAudioUrl}
          />
        )}
      </div>
    </section>
  )
}

function uploadError(status?: number): string {
  if (status === 413) return 'Áudio maior que o limite permitido. Grave um trecho mais curto.'
  if (status === 415) return 'Formato não aceito pelo servidor. Use outro navegador para gravar.'
  if (status === 422) return 'Áudio inválido ou com duração real acima do limite. Baixe sua gravação e grave um trecho mais curto.'
  if (status === 401 || status === 403) return 'Sua sessão precisa ser confirmada antes de tentar novamente.'
  if (status === 409) return 'Esta tentativa já contém outro áudio; nada foi sobrescrito.'
  if (status === 408) return 'O envio demorou demais. Tente novamente.'
  return 'Não foi possível confirmar o envio. Tente novamente.'
}

function ratingLabel(value: NonNullable<SpeakingAttempt['self_rating']>): string {
  return value === 'repeat' ? 'Quero repetir' : value === 'almost' ? 'Quase lá' : 'Confiante'
}
