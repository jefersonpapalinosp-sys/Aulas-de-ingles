import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import { api, authenticatedFetch, type LessonMedia } from '../../api/client'
import { useAssistStatus } from '../../api/assist'
import { invalidateStudy } from '../../api/invalidateStudy'
import { formatAudioTime } from '../media/LessonAudioPlayer'
import { writeLocal } from '../../storage/local'
import { sessionSnapshot } from '../../api/session'
import { readSelfRating, selfRatingKey } from './selfRating'
import { ShadowingRecorder } from './ShadowingRecorder'
import { SpeakingAttemptList } from './SpeakingAttemptList'
import { SpeakingUpload, type SelfRating } from './speakingUpload'
import { recordingTypes, VoiceRecorder } from './voiceRecorder'

type RecordingStatus = 'idle' | 'requesting' | 'recording' | 'ready' | 'error'

/** Shadowing: ouvir o modelo, repetir, comparar e — só com consentimento — enviar.
 *
 * O envio saiu daqui para `speakingUpload.ts`, que é onde moram os dois passos,
 * o reaproveitamento da tentativa quando a resposta se perde e a travessia de
 * sessão. Este componente cuida da gravação, da autoavaliação e da tela.
 */
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
  const modelRef = useRef<HTMLAudioElement>(null)
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
  const upload = useMemo(() => new SpeakingUpload(userId, {
    createAttempt: async (body, signal) => {
      const { data, response } = await api.POST('/api/speaking/attempts', { body, signal })
      return data ? { id: data.id } : { status: response?.status }
    },
    putAudio: async (attemptId, blob, signal) => {
      const sent = await authenticatedFetch(`/api/speaking/attempts/${attemptId}/audio`, {
        method: 'PUT',
        headers: { 'Content-Type': blob.type },
        body: blob,
        signal,
      })
      return { ok: sent.ok, status: sent.status }
    },
    session: sessionSnapshot,
  }), [userId])
  const sending = useSyncExternalStore(upload.subscribe, upload.snapshot)
  const cue = media.cues.find((item) => item.id === cueId) ?? firstCue
  const draftKey = `${userId}:${courseSlug}:${lessonNumber}:${cue?.id}`
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
    upload.reset()
    if (!cue) return
    if (modelRef.current && !modelRef.current.paused) modelRef.current.pause()
    const avaliacao = readSelfRating(userId, courseSlug, lessonNumber, cue.id)
    setStorageWarning(avaliacao.warning)
    setRating(avaliacao.rating)
    setRecordingUrl(null)
    setRecordingBlob(null)
    setRecordingDuration(0)
    setConsent(false)
    setStatus('idle')
    setMessage('')
    const restored = upload.recover(draftKey)
    const restoredUrl = restored ? URL.createObjectURL(restored.blob) : null
    if (restored) {
      setRecordingBlob(restored.blob)
      setRecordingDuration(restored.duration)
      setRecordingUrl(restoredUrl)
      setStatus('ready')
      setMessage('Gravação recuperada nesta aba. Confira e autorize o envio novamente.')
    }
    return () => {
      recorder.cancel()
      upload.reset()
      // StrictMode pode limpar este efeito antes de o estado publicar a primeira URL.
      if (restoredUrl) URL.revokeObjectURL(restoredUrl)
    }
  }, [courseSlug, cue, lessonNumber, userId, recorder, upload, draftKey])

  useEffect(() => () => {
    if (recordingUrl && typeof URL.revokeObjectURL === 'function') URL.revokeObjectURL(recordingUrl)
  }, [recordingUrl])

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
    if (!supported || sending.saving) return
    upload.discard(draftKey)
    setStatus('requesting')
    setMessage('Solicitando acesso ao microfone…')
    setRecordingUrl(null)
    setRecordingBlob(null)
    setConsent(false)
    await recorder.start(maxDuration, policy?.mime_types ?? recordingTypes.map((type) => type.split(';')[0]!))
  }

  function saveRating(value: SelfRating) {
    if (!cue) return
    setRating(value)
    const result = writeLocal(selfRatingKey(userId, courseSlug, lessonNumber, cue.id), value)
    setStorageWarning(result.ok ? '' : result.error)
    setMessage(result.ok ? 'Autoavaliação salva neste navegador.' : 'Autoavaliação apenas nesta tela; não foi salva neste navegador.')
  }

  function discardLocal() {
    upload.discard(draftKey)
    recorder.cancel()
    setRecordingUrl(null)
    setRecordingBlob(null)
    setRecordingDuration(0)
    setConsent(false)
    setStatus('idle')
    setMessage('Gravação local descartada.')
  }

  async function saveRecording() {
    if (!cue || !recordingBlob || !consent || sending.saved || !policy) return
    setMessage('Salvando gravação com segurança…')
    const result = await upload.save({
      key: draftKey, cueId: cue.id, blob: recordingBlob, duration: recordingDuration, rating,
    })
    if (result.message) setMessage(result.message)
    if (!result.ok) return
    setConsent(false)
    await invalidateStudy(queryClient, 'speakingUpload')
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
      <p className="study-copy">
        A avaliação oral é sua autoavaliação após ouvir e comparar. A transcrição automática,
        quando ativada, transforma fala em texto, mas não dá nota de pronúncia nem substitui
        a escuta de um professor.
      </p>

      <label className="shadowing-select">
        Frase para praticar
        <select
          value={cue.id}
          disabled={sending.saving || status === 'requesting' || status === 'recording'}
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
            disabled={!supported || sending.saving || status === 'requesting'}
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
      {message && <p className="shadowing-status" role="status">{message}</p>}

      {recordingUrl && (
        <ShadowingRecorder
          recordingUrl={recordingUrl}
          recordingBlob={recordingBlob}
          policy={policy}
          rating={rating}
          consent={consent}
          saving={sending.saving}
          saved={sending.saved}
          pending={sending.pending}
          onRating={saveRating}
          onConsent={setConsent}
          onSave={() => void saveRecording()}
          onDiscard={discardLocal}
        />
      )}

      <SpeakingAttemptList
        userId={userId}
        courseSlug={courseSlug}
        lessonNumber={lessonNumber}
        assist={assistStatus.data}
        announce={setMessage}
      />
    </section>
  )
}
