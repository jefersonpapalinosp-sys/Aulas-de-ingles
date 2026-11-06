import { AudioControls, AudioElement } from './AudioPlayback'
import { useEffect, useRef, useState } from 'react'
import type { LessonMedia } from '../../api/client'
import { useMediaPositionSync } from '../../api/media'
import { CueTranscript, FullTranscript } from './AudioTranscripts'
import { formatAudioTime } from './formatAudioTime'

// A barra do shadowing e a página de estudo já importavam o formatador daqui.
export { formatAudioTime } from './formatAudioTime'

type LessonAudioPlayerProps = {
  media: LessonMedia
  userId: number
  sourcePageUrl: string
}

export function LessonAudioPlayer(props: LessonAudioPlayerProps) {
  return <LessonAudioPlayerContent key={`${props.userId}:${props.media.id}`} {...props} />
}

function LessonAudioPlayerContent({
  media,
  userId,
  sourcePageUrl,
}: LessonAudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const lastSavedAt = useRef(0)
  const touched = useRef(false)
  const ended = useRef(false)
  const [metadataReady, setMetadataReady] = useState(false)
  const [position, setPosition] = useState(0)
  const [duration, setDuration] = useState(media.duration_seconds ?? 0)
  const [rate, setRate] = useState(1)
  const [loopStart, setLoopStart] = useState<number | null>(null)
  const [loopEnd, setLoopEnd] = useState<number | null>(null)
  const [failed, setFailed] = useState(false)
  const [transcriptOpen, setTranscriptOpen] = useState(false)
  const [translationOpen, setTranslationOpen] = useState(false)
  const [fullTranscriptOpen, setFullTranscriptOpen] = useState(false)
  const sync = useMediaPositionSync(media.id, userId)
  const activeCue = media.cues.find(
    (cue) => position >= cue.start_seconds && position < cue.end_seconds,
  )

  useEffect(() => {
    const audio = audioRef.current
    if (!audio || !metadataReady || !sync.ready || touched.current) return
    const saved = sync.completed ? 0 : sync.position
    if (saved >= 0 && saved < duration - 2) {
      audio.currentTime = saved
      setPosition(saved)
      lastSavedAt.current = saved
    }
  }, [duration, metadataReady, sync.position, sync.completed, sync.ready])

  function persistPosition(at: number) {
    touched.current = true
    lastSavedAt.current = at
    sync.record(at)
  }

  function onLoadedMetadata() {
    const audio = audioRef.current
    if (!audio) return
    if (Number.isFinite(audio.duration)) setDuration(audio.duration)
    setMetadataReady(true)
  }

  async function resolvePosition(choice: 'local' | 'remote') {
    await sync.resolve(choice)
    if (sync.snapshot().conflict) return
    const saved = sync.snapshot().position
    if (audioRef.current) audioRef.current.currentTime = saved
    setPosition(saved)
    lastSavedAt.current = saved
  }

  function onTimeUpdate() {
    const audio = audioRef.current
    if (!audio || ended.current || audio.ended) return

    if (loopStart !== null && loopEnd !== null && audio.currentTime >= loopEnd) {
      audio.currentTime = loopStart
    }

    setPosition(audio.currentTime)
    if (Math.abs(audio.currentTime - lastSavedAt.current) >= 5) {
      persistPosition(audio.currentTime)
    }
  }

  function skip(seconds: number) {
    const audio = audioRef.current
    if (!audio) return
    const upper = Number.isFinite(audio.duration) ? audio.duration : duration
    audio.currentTime = Math.max(0, Math.min(audio.currentTime + seconds, upper || Infinity))
    ended.current = false
    setPosition(audio.currentTime)
    persistPosition(audio.currentTime)
  }

  function changeRate(value: number) {
    const audio = audioRef.current
    if (audio) audio.playbackRate = value
    setRate(value)
  }

  function clearLoop() {
    setLoopStart(null)
    setLoopEnd(null)
  }

  function seekToCue(startSeconds: number) {
    const audio = audioRef.current
    if (!audio) return
    ended.current = false
    audio.currentTime = startSeconds
    setPosition(startSeconds)
    persistPosition(startSeconds)
  }

  return (
    <section className="audio-player" aria-labelledby={`audio-title-${media.id}`}>
      <div className="audio-player-head">
        <div>
          <p className="study-kicker">Listening · áudio oficial da VOA</p>
          <h2 id={`audio-title-${media.id}`}>{media.label}</h2>
        </div>
        <span className="audio-time" aria-live="off">
          {formatAudioTime(position)} / {formatAudioTime(duration)}
        </span>
      </div>

      <AudioElement
        audioRef={audioRef} src={media.source_url}
        controls
        preload="metadata"
        aria-label={media.label}
        onLoadedMetadata={onLoadedMetadata}
        onTimeUpdate={onTimeUpdate}
        onPlay={() => { touched.current = true; ended.current = false }}
        onPause={() => {
          if (!ended.current && !audioRef.current?.ended) persistPosition(audioRef.current?.currentTime ?? position)
        }}
        onEnded={() => {
          ended.current = true
          touched.current = true
          sync.finish()
          lastSavedAt.current = 0
          setPosition(0)
        }}
        onError={() => setFailed(true)}
      />

      <p className="muted">Áudio online · não baixado neste dispositivo.</p>
      <details className="media-rights">
        <summary>Fonte, licença e uso offline</summary>
        <p>
          <strong>{media.attribution}.</strong> {media.license_note}
        </p>
        <p>
          {media.offline_policy === 'network_only'
            ? 'Reprodução somente online: o aplicativo não armazena este áudio no cache.'
            : 'A licença permite cache, mas este aplicativo ainda não oferece download offline desta mídia.'}{' '}
          {media.license_url && (
            <a href={media.license_url} target="_blank" rel="noopener noreferrer">
              Consultar os termos da fonte
            </a>
          )}
        </p>
      </details>

      <p className="media-sync" aria-live="polite">
        {sync.pending > 0 ? `${sync.pending} posição(ões) com sincronização pendente.`
          : sync.confirmed ? 'Posição sincronizada com sua conta.'
            : sync.ready ? 'Posição disponível neste dispositivo; conta ainda não confirmada.' : 'Consultando posição da conta…'}
      </p>
      {sync.warning && <p className="erro" role="alert">{sync.warning}</p>}
      {sync.error && <p role="status">{sync.error} <button type="button" onClick={() => void sync.retry()}>Tentar sincronizar</button></p>}
      {sync.conflict && (
        <section className="media-fallback" aria-label="Conflito de posição">
          <h3>Há duas posições de retomada</h3>
          <p>Neste dispositivo: {formatAudioTime(sync.position)}{sync.completed ? ' (concluído)' : ''}.
            Na conta: {formatAudioTime(sync.conflict.position_seconds)}{sync.conflict.completed ? ' (concluído)' : ''}.
            Escolha a retomada. Nenhuma posição foi substituída.</p>
          <button type="button" onClick={() => void resolvePosition('local')}>Manter posição deste dispositivo</button>{' '}
          <button type="button" onClick={() => void resolvePosition('remote')}>Usar posição da conta</button>
        </section>
      )}

      <AudioControls rate={rate} position={position} loopStart={loopStart} loopEnd={loopEnd}
        onSkip={skip} onRate={changeRate} onClear={clearLoop}
        onStart={() => { setLoopStart(audioRef.current?.currentTime ?? 0); setLoopEnd(null) }}
        onEnd={() => setLoopEnd(audioRef.current?.currentTime ?? position)} />

      {failed && (
        <p className="audio-error" role="alert">
          Não foi possível carregar o áudio aqui.{' '}
          <a href={media.source_url} target="_blank" rel="noopener noreferrer">
            Abrir o MP3 na fonte
          </a>
          .
        </p>
      )}

      <CueTranscript
        cues={media.cues}
        open={transcriptOpen}
        translated={translationOpen}
        activeCueId={activeCue?.id}
        onToggle={() => setTranscriptOpen((open) => !open)}
        onTranslate={setTranslationOpen}
        onSeek={seekToCue}
      />

      <FullTranscript
        lines={media.transcript}
        open={fullTranscriptOpen}
        sourcePageUrl={sourcePageUrl}
        onToggle={() => setFullTranscriptOpen((open) => !open)}
      />

    </section>
  )
}
