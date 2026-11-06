import { useEffect, useRef, useState } from 'react'
import { authenticatedFetch } from '../../api/client'
import type { NativeActivity } from '../../api/nativeListening'
import { AudioControls, AudioElement } from './AudioPlayback'
import { useNativePosition } from '../../api/nativePosition'
import { formatAudioTime } from './formatAudioTime'

export function NativeAudioPlayer({ activity, userId, sessionId }: { activity: NativeActivity; userId: number; sessionId: number }) {
  const ref = useRef<HTMLAudioElement>(null)
  const touched = useRef(false)
  const ended = useRef(false)
  const savedAt = useRef(0)
  const [metadata, setMetadata] = useState(false)
  const sync = useNativePosition(userId, sessionId, activity.version)
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [rate, setRate] = useState(1)
  const [position, setPosition] = useState(0)
  const [start, setStart] = useState<number | null>(null)
  const [end, setEnd] = useState<number | null>(null)
  useEffect(() => {
    if (!metadata || !sync.ready || touched.current || !ref.current) return
    const position = sync.completed ? 0 : Math.min(sync.position, activity.audio_duration_seconds)
    ref.current.currentTime = position; savedAt.current = position; setPosition(position)
  }, [metadata, sync.ready, sync.position, sync.completed, activity.audio_duration_seconds])
  function record(at: number, completed = false) {
    touched.current = true; savedAt.current = at
    void sync.record(at, completed)
  }
  useEffect(() => {
    const controller = new AbortController()
    let objectUrl: string | null = null
    setUrl(null); setFailed(false); setMetadata(false)
    void authenticatedFetch(`/api/listening/native/${activity.slug}/versions/${activity.version}/audio`, {
      signal: controller.signal, cache: 'no-store',
    }).then(async response => {
      if (!response.ok) throw new Error('audio_unavailable')
      const blob = await response.blob()
      if (controller.signal.aborted) return
      objectUrl = URL.createObjectURL(blob)
      setUrl(objectUrl)
    }).catch(() => { if (!controller.signal.aborted) setFailed(true) })
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [activity.slug, activity.version, attempt])
  return <section className="audio-player" aria-label="Áudio da atividade">
    {!url && !failed && <p role="status">Carregando áudio…</p>}
    {failed && <p role="alert">Áudio indisponível. <button type="button" onClick={() => setAttempt(n => n + 1)}>Tentar carregar áudio</button></p>}
    {url && <>
      <AudioElement src={url} audioRef={ref} aria-label={activity.title}
        onLoadedMetadata={() => { if (ref.current) ref.current.playbackRate = rate; setMetadata(true) }}
        onPlay={() => { touched.current = true; ended.current = false }}
        onPause={() => { if (touched.current && !ended.current && ref.current && !ref.current.ended) record(ref.current.currentTime) }}
        onEnded={() => { ended.current = true; record(0, true); setPosition(0) }}
        onError={() => setFailed(true)} onTimeUpdate={() => {
          const audio = ref.current
          if (!audio || ended.current) return
          if (start !== null && end !== null && audio.currentTime >= end) audio.currentTime = start
          setPosition(audio.currentTime)
          if (touched.current && Math.abs(audio.currentTime - savedAt.current) >= 5) record(audio.currentTime)
        }} />
      <AudioControls rate={rate} position={position} loopStart={start} loopEnd={end}
        onSkip={seconds => { if (ref.current) { ref.current.currentTime = Math.max(0, Math.min(ref.current.currentTime + seconds, activity.audio_duration_seconds)); ended.current = false; record(ref.current.currentTime) } }}
        onRate={value => { setRate(value); if (ref.current) ref.current.playbackRate = value }}
        onStart={() => { setStart(ref.current?.currentTime ?? 0); setEnd(null) }}
        onEnd={() => setEnd(ref.current?.currentTime ?? position)} onClear={() => { setStart(null); setEnd(null) }} />
    </>}
    <p>{activity.attribution}</p><p className="muted">{activity.rights_note}</p>
    <p role="status">{sync.confirmed ? 'Posição confirmada na conta.' : sync.pending ? 'Posição pendente de sincronização.' : 'Consultando posição do áudio…'}</p>
    {(sync.error || sync.warning) && <p role="alert">{sync.error || sync.warning} <button type="button" onClick={() => void sync.retry()}>Sincronizar posição</button></p>}
    {sync.conflict && <div role="alert"><p>Há duas posições: neste dispositivo {formatAudioTime(sync.position)}; na conta {formatAudioTime(sync.conflict.position_seconds)}.</p>
      {(['local', 'remote'] as const).map(choice => <button key={choice} type="button" onClick={() => {
        void sync.resolve(choice).then(() => { if (!sync.snapshot().conflict && ref.current) { ref.current.currentTime = sync.snapshot().position; setPosition(sync.snapshot().position) } })
      }}>{choice === 'local' ? 'Manter posição deste dispositivo' : 'Usar posição da conta'}</button>)}
    </div>}
    <p className="muted">Áudio somente online. A transcrição pode ser revelada como apoio.</p>
  </section>
}
