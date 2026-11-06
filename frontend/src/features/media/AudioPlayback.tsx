import type { ComponentProps, Ref } from 'react'
import { formatAudioTime } from './formatAudioTime'

export function AudioElement({ src, audioRef, ...props }: ComponentProps<'audio'> & {
  src: string; audioRef: Ref<HTMLAudioElement>
}) {
  // A transcrição é oferecida pelo fluxo de estudo que usa este player.
  return <audio {...props} ref={audioRef} controls preload="metadata">{/* eslint-disable-line jsx-a11y/media-has-caption */}
    <source src={src} type="audio/mpeg" />
    Seu navegador não consegue reproduzir este áudio.
  </audio>
}

export function AudioControls({ rate, position, loopStart, loopEnd, onSkip, onRate,
  onStart, onEnd, onClear }: {
  rate: number; position: number; loopStart: number | null; loopEnd: number | null
  onSkip: (seconds: number) => void; onRate: (rate: number) => void
  onStart: () => void; onEnd: () => void; onClear: () => void
}) {
  return <>
    <div className="audio-toolbar" aria-label="Controles adicionais do áudio">
      <button type="button" onClick={() => onSkip(-5)}>−5 s</button>
      <button type="button" onClick={() => onSkip(5)}>+5 s</button>
      <label>Velocidade<select aria-label="Velocidade do áudio" value={rate}
        onChange={event => onRate(Number(event.target.value))}>
        {[0.75, 1, 1.25, 1.5].map(value => <option key={value} value={value}>{value}×</option>)}
      </select></label>
    </div>
    <div className="audio-loop" aria-label="Repetição de trecho">
      <button type="button" onClick={onStart}>Marcar início A</button>
      <button type="button" disabled={loopStart === null || position <= loopStart} onClick={onEnd}>Marcar fim B</button>
      {(loopStart !== null || loopEnd !== null) && <>
        <span>A {formatAudioTime(loopStart ?? 0)}{loopEnd !== null && ` · B ${formatAudioTime(loopEnd)}`}</span>
        <button type="button" onClick={onClear}>Limpar trecho</button>
      </>}
    </div>
  </>
}
