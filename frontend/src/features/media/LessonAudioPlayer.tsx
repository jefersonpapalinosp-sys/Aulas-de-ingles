import { useRef, useState } from 'react'
import type { LessonMedia } from '../../api/client'

function positionKey(userId: number, mediaId: number): string {
  return `aulas-ingles:media-position:v1:${userId}:${mediaId}`
}

export function formatAudioTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00'
  const whole = Math.floor(seconds)
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`
}

export function LessonAudioPlayer({ media, userId }: { media: LessonMedia; userId: number }) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const lastSavedAt = useRef(0)
  const [position, setPosition] = useState(0)
  const [duration, setDuration] = useState(media.duration_seconds ?? 0)
  const [rate, setRate] = useState(1)
  const [loopStart, setLoopStart] = useState<number | null>(null)
  const [loopEnd, setLoopEnd] = useState<number | null>(null)
  const [failed, setFailed] = useState(false)
  const [transcriptOpen, setTranscriptOpen] = useState(false)
  const [translationOpen, setTranslationOpen] = useState(false)
  const activeCue = media.cues.find(
    (cue) => position >= cue.start_seconds && position < cue.end_seconds,
  )

  function persistPosition(at: number) {
    window.localStorage.setItem(positionKey(userId, media.id), String(at))
    lastSavedAt.current = at
  }

  function onLoadedMetadata() {
    const audio = audioRef.current
    if (!audio) return
    if (Number.isFinite(audio.duration)) setDuration(audio.duration)

    const saved = Number(window.localStorage.getItem(positionKey(userId, media.id)))
    if (Number.isFinite(saved) && saved > 0 && saved < audio.duration - 2) {
      audio.currentTime = saved
      setPosition(saved)
      lastSavedAt.current = saved
    }
  }

  function onTimeUpdate() {
    const audio = audioRef.current
    if (!audio) return

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
    setPosition(audio.currentTime)
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

      <audio
        ref={audioRef}
        controls
        preload="metadata"
        aria-label={media.label}
        onLoadedMetadata={onLoadedMetadata}
        onTimeUpdate={onTimeUpdate}
        onPause={() => persistPosition(audioRef.current?.currentTime ?? position)}
        onEnded={() => {
          window.localStorage.removeItem(positionKey(userId, media.id))
          setPosition(0)
        }}
        onError={() => setFailed(true)}
      >
        <source src={media.source_url} type="audio/mpeg" />
        Seu navegador não consegue reproduzir este áudio.
      </audio>

      <div className="audio-toolbar" aria-label="Controles adicionais do áudio">
        <button type="button" onClick={() => skip(-5)}>
          −5 s
        </button>
        <button type="button" onClick={() => skip(5)}>
          +5 s
        </button>
        <label>
          Velocidade
          <select
            aria-label="Velocidade do áudio"
            value={rate}
            onChange={(event) => changeRate(Number(event.target.value))}
          >
            {[0.75, 1, 1.25, 1.5].map((value) => (
              <option key={value} value={value}>
                {value}×
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="audio-loop" aria-label="Repetição de trecho">
        <button
          type="button"
          onClick={() => {
            setLoopStart(audioRef.current?.currentTime ?? 0)
            setLoopEnd(null)
          }}
        >
          Marcar início A
        </button>
        <button
          type="button"
          disabled={loopStart === null || position <= loopStart}
          onClick={() => setLoopEnd(audioRef.current?.currentTime ?? position)}
        >
          Marcar fim B
        </button>
        {(loopStart !== null || loopEnd !== null) && (
          <>
            <span>
              A {formatAudioTime(loopStart ?? 0)}
              {loopEnd !== null && ` · B ${formatAudioTime(loopEnd)}`}
            </span>
            <button type="button" onClick={clearLoop}>
              Limpar trecho
            </button>
          </>
        )}
      </div>

      {failed && (
        <p className="audio-error" role="alert">
          Não foi possível carregar o áudio aqui.{' '}
          <a href={media.source_url} target="_blank" rel="noopener noreferrer">
            Abrir o MP3 na fonte
          </a>
          .
        </p>
      )}

      {media.cues.length > 0 && (
        <div className="audio-transcript">
          <div className="audio-transcript-head">
            <div>
              <p className="study-kicker">Trechos selecionados</p>
              <h3>Transcrição de estudo</h3>
            </div>
            <button
              type="button"
              className="transcript-toggle"
              aria-expanded={transcriptOpen}
              onClick={() => setTranscriptOpen((open) => !open)}
            >
              {transcriptOpen ? 'Ocultar transcrição' : 'Mostrar transcrição'}
            </button>
          </div>

          {transcriptOpen && (
            <>
              <label className="translation-toggle">
                <input
                  type="checkbox"
                  checked={translationOpen}
                  onChange={(event) => setTranslationOpen(event.target.checked)}
                />
                Mostrar apoio em português
              </label>
              <ol className="transcript-cues">
                {media.cues.map((cue) => {
                  const active = activeCue?.id === cue.id
                  return (
                    <li key={cue.id} className={active ? 'active' : ''}>
                      <button
                        type="button"
                        aria-current={active ? 'true' : undefined}
                        aria-label={`Ir para ${formatAudioTime(cue.start_seconds)} — ${cue.speaker}`}
                        onClick={() => seekToCue(cue.start_seconds)}
                      >
                        <span className="cue-time">{formatAudioTime(cue.start_seconds)}</span>
                        <span className="cue-copy">
                          <strong>{cue.speaker}</strong>
                          <span lang="en">{cue.text_en}</span>
                          {translationOpen && <small lang="pt-BR">{cue.text_pt}</small>}
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ol>
            </>
          )}
        </div>
      )}
    </section>
  )
}
