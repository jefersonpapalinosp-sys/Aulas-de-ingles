import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  api,
  authenticatedFetch,
  type LessonMedia,
  type SpeakingAttempt,
} from '../../api/client'
import { useAssistStatus } from '../../api/assist'
import { formatAudioTime } from '../media/LessonAudioPlayer'

type RecordingStatus = 'idle' | 'requesting' | 'recording' | 'ready' | 'error'
type SelfRating = 'repeat' | 'almost' | 'confident'

function ratingKey(userId: number, lessonNumber: number, cueId: number): string {
  return `aulas-ingles:shadowing-rating:v1:${userId}:${lessonNumber}:${cueId}`
}

export function ShadowingPractice({
  media,
  userId,
  lessonNumber,
}: {
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
  const [modelPlaying, setModelPlaying] = useState(false)
  const [rating, setRating] = useState<SelfRating | null>(null)
  const [consent, setConsent] = useState(false)
  const [saving, setSaving] = useState(false)
  const [savedCurrent, setSavedCurrent] = useState(false)
  const [savedAudioUrl, setSavedAudioUrl] = useState<string | null>(null)
  const [playingAttemptId, setPlayingAttemptId] = useState<number | null>(null)
  const modelRef = useRef<HTMLAudioElement>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const stopTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const recordingStartedAtRef = useRef(0)
  const cue = media.cues.find((item) => item.id === cueId) ?? firstCue
  const historyKey = useMemo(
    () => ['speaking-attempts', userId, lessonNumber] as const,
    [lessonNumber, userId],
  )
  const historyQuery = useQuery({
    queryKey: historyKey,
    queryFn: async () => {
      const { data } = await api.GET('/api/speaking/attempts', {
        params: { query: { lesson: lessonNumber } },
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
  const supported =
    typeof navigator !== 'undefined' &&
    typeof navigator.mediaDevices?.getUserMedia === 'function' &&
    typeof MediaRecorder !== 'undefined'

  useEffect(() => {
    if (!cue) return
    if (modelRef.current && !modelRef.current.paused) modelRef.current.pause()
    const saved = window.localStorage.getItem(ratingKey(userId, lessonNumber, cue.id))
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
  }, [cue, lessonNumber, userId])

  useEffect(
    () => () => {
      if (stopTimerRef.current) clearTimeout(stopTimerRef.current)
      const recorder = recorderRef.current
      if (recorder?.state === 'recording') {
        recorder.ondataavailable = null
        recorder.onstop = null
        recorder.stop()
      }
      streamRef.current?.getTracks().forEach((track) => track.stop())
    },
    [],
  )

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

  function stopStream() {
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
  }

  function stopRecording() {
    if (stopTimerRef.current) clearTimeout(stopTimerRef.current)
    stopTimerRef.current = null
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
  }

  async function startRecording() {
    if (!supported) return
    setStatus('requesting')
    setMessage('Solicitando acesso ao microfone…')
    setRecordingUrl(null)
    setRecordingBlob(null)
    setConsent(false)
    setSavedCurrent(false)

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      const recorder = new MediaRecorder(stream)
      const chunks: Blob[] = []
      recorderRef.current = recorder
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunks.push(event.data)
      }
      recorder.onstop = () => {
        stopStream()
        if (chunks.length === 0) {
          setStatus('error')
          setMessage('O navegador não produziu áudio. Tente gravar novamente.')
          return
        }
        const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' })
        setRecordingBlob(blob)
        setRecordingDuration(Math.max(1, Math.min(30_000, Date.now() - recordingStartedAtRef.current)))
        setRecordingUrl(URL.createObjectURL(blob))
        setStatus('ready')
        setMessage('Gravação pronta. Compare sua voz com o modelo.')
      }
      recorder.start()
      recordingStartedAtRef.current = Date.now()
      setStatus('recording')
      setMessage('Gravando… fale a frase e pare quando terminar.')
      stopTimerRef.current = setTimeout(stopRecording, 30_000)
    } catch {
      stopStream()
      setStatus('error')
      setMessage('Não foi possível acessar o microfone. Confira a permissão do navegador.')
    }
  }

  function saveRating(value: SelfRating) {
    if (!cue) return
    setRating(value)
    window.localStorage.setItem(ratingKey(userId, lessonNumber, cue.id), value)
    setMessage('Autoavaliação salva neste navegador.')
  }

  function discardLocal() {
    setRecordingUrl(null)
    setRecordingBlob(null)
    setRecordingDuration(0)
    setConsent(false)
    setSavedCurrent(false)
    setStatus('idle')
    setMessage('Gravação local descartada.')
  }

  async function saveRecording() {
    if (!cue || !recordingBlob || !consent || savedCurrent) return
    setSaving(true)
    setMessage('Salvando gravação com segurança…')
    let attemptId: number | null = null
    try {
      const { data: attempt } = await api.POST('/api/speaking/attempts', {
        body: {
          cue_id: cue.id,
          duration_ms: recordingDuration,
          self_rating: rating,
          consent: true,
        },
      })
      if (!attempt) throw new Error('Falha ao registrar a gravação.')
      attemptId = attempt.id
      const upload = await authenticatedFetch(`/api/speaking/attempts/${attempt.id}/audio`, {
        method: 'PUT',
        headers: { 'Content-Type': recordingBlob.type || 'audio/webm' },
        body: recordingBlob,
      })
      if (!upload.ok) throw new Error('Falha ao enviar o áudio.')
      setSavedCurrent(true)
      setConsent(false)
      setMessage('Gravação salva na sua conta. Você pode ouvi-la ou excluí-la abaixo.')
      await queryClient.invalidateQueries({ queryKey: historyKey })
    } catch {
      if (attemptId !== null) {
        await api.DELETE('/api/speaking/attempts/{attempt_id}', {
          params: { path: { attempt_id: attemptId } },
        })
      }
      setMessage('Não foi possível salvar. O áudio continua apenas nesta tela.')
    } finally {
      setSaving(false)
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
    await queryClient.invalidateQueries({ queryKey: historyKey })
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
    await queryClient.invalidateQueries({ queryKey: historyKey })
  }

  return (
    <section className="shadowing-card" aria-labelledby="shadowing-title">
      <p className="study-kicker">Speaking · shadowing</p>
      <h2 id="shadowing-title">Escute, repita e compare sua voz</h2>
      <p className="study-copy">
        Por padrão, a gravação fica somente nesta tela e é descartada ao sair. Ela só será
        enviada se você marcar o consentimento e escolher salvar na sua conta.
      </p>

      <label className="shadowing-select">
        Frase para praticar
        <select
          value={cue.id}
          disabled={status === 'requesting' || status === 'recording'}
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
          <button type="button" className="btn recording" onClick={stopRecording}>
            Parar gravação
          </button>
        ) : (
          <button
            type="button"
            className="btn"
            disabled={!supported || status === 'requesting'}
            onClick={() => void startRecording()}
          >
            {status === 'requesting' ? 'Abrindo microfone…' : '2. Gravar minha voz'}
          </button>
        )}
      </div>

      {!supported && (
        <p className="shadowing-warning" role="alert">
          Este navegador não oferece gravação de áudio. Você ainda pode ouvir o modelo e repetir
          em voz alta.
        </p>
      )}
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
                recordingBlob.size > 2_000_000
              }
              onClick={() => void saveRecording()}
            >
              {saving ? 'Salvando…' : savedCurrent ? 'Gravação salva' : 'Salvar na minha conta'}
            </button>
            <button type="button" className="btn ghost" disabled={saving} onClick={discardLocal}>
              Descartar gravação local
            </button>
          </div>
          {recordingBlob && recordingBlob.size > 2_000_000 && (
            <p className="shadowing-warning" role="alert">
              O arquivo passou de 2 MB. Faça uma tentativa mais curta para salvar.
            </p>
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
            {assistStatus.data.retention_days} dias. Restam {assistStatus.data.remaining_today}{' '}
            análises hoje.
          </p>
        )}
        {historyQuery.isPending && <p>Carregando histórico…</p>}
        {historyQuery.isError && <p>Não foi possível carregar o histórico.</p>}
        {historyQuery.data?.length === 0 && <p>Nenhuma gravação salva.</p>}
        {historyQuery.data && historyQuery.data.length > 0 && (
          <ul>
            {historyQuery.data.map((attempt) => (
              <li key={attempt.id}>
                <div>
                  <strong lang="en">{attempt.cue_text}</strong>
                  <small>
                    {new Intl.DateTimeFormat('pt-BR', {
                      dateStyle: 'short',
                      timeStyle: 'short',
                    }).format(new Date(attempt.created_at))}
                    {attempt.self_rating ? ` · ${ratingLabel(attempt.self_rating)}` : ''}
                  </small>
                </div>
                <button type="button" onClick={() => void playSaved(attempt)}>Ouvir</button>
                <button type="button" onClick={() => void deleteSaved(attempt.id)}>Excluir</button>
                {assistStatus.data?.transcription_enabled && !attempt.transcription && (
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
                    {['queued', 'processing'].includes(attempt.transcription.status) && (
                      <p role="status">Transcrição em processamento…</p>
                    )}
                    {attempt.transcription.status === 'failed' && (
                      <p role="alert">
                        A transcrição falhou. A gravação e sua autoavaliação não foram perdidas.
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

function ratingLabel(value: NonNullable<SpeakingAttempt['self_rating']>): string {
  return value === 'repeat' ? 'Quero repetir' : value === 'almost' ? 'Quase lá' : 'Confiante'
}
