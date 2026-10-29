import type { LessonMedia } from '../../api/client'
import { formatAudioTime } from './formatAudioTime'

/** Trechos selecionados, com o apoio em português atrás de uma escolha.
 *
 * A tradução vem fechada de propósito: ler o português junto do inglês é o
 * caminho mais curto para não escutar. Clicar num trecho leva o áudio até ele.
 */
export function CueTranscript({
  cues, open, translated, activeCueId, onToggle, onTranslate, onSeek,
}: {
  cues: LessonMedia['cues']
  open: boolean
  translated: boolean
  activeCueId?: number
  onToggle: () => void
  onTranslate: (value: boolean) => void
  onSeek: (seconds: number) => void
}) {
  if (cues.length === 0) return null
  return (
    <div className="audio-transcript">
      <div className="audio-transcript-head">
        <div>
          <p className="study-kicker">Trechos selecionados</p>
          <h3>Transcrição de estudo</h3>
        </div>
        <button type="button" className="transcript-toggle" aria-expanded={open} onClick={onToggle}>
          {open ? 'Ocultar transcrição' : 'Mostrar transcrição'}
        </button>
      </div>

      {open && (
        <>
          <label className="translation-toggle">
            <input
              type="checkbox"
              checked={translated}
              onChange={(event) => onTranslate(event.target.checked)}
            />
            Mostrar apoio em português
          </label>
          <ol className="transcript-cues">
            {cues.map((cue) => {
              const active = activeCueId === cue.id
              return (
                <li key={cue.id} className={active ? 'active' : ''}>
                  <button
                    type="button"
                    aria-current={active ? 'true' : undefined}
                    aria-label={`Ir para ${formatAudioTime(cue.start_seconds)} — ${cue.speaker}`}
                    onClick={() => onSeek(cue.start_seconds)}
                  >
                    <span className="cue-time">{formatAudioTime(cue.start_seconds)}</span>
                    <span className="cue-copy">
                      <strong>{cue.speaker}</strong>
                      <span lang="en">{cue.text_en}</span>
                      {translated && <small lang="pt-BR">{cue.text_pt}</small>}
                    </span>
                  </button>
                </li>
              )
            })}
          </ol>
        </>
      )}
    </div>
  )
}

/** Conversa completa em inglês, com o crédito da fonte em domínio público. */
export function FullTranscript({
  lines, open, sourcePageUrl, onToggle,
}: {
  lines: LessonMedia['transcript']
  open: boolean
  sourcePageUrl: string
  onToggle: () => void
}) {
  if (lines.length === 0) return null
  return (
    <div className="audio-transcript full-transcript">
      <div className="audio-transcript-head">
        <div>
          <p className="study-kicker">Conversa completa</p>
          <h3>Transcrição integral em inglês</h3>
        </div>
        <button type="button" className="transcript-toggle" aria-expanded={open} onClick={onToggle}>
          {open ? 'Ocultar texto integral' : 'Mostrar texto integral'}
        </button>
      </div>

      {open && (
        <>
          <p className="transcript-credit">
            Fonte: conteúdo em domínio público da{' '}
            <a href={sourcePageUrl} target="_blank" rel="noopener noreferrer">
              VOA Learning English
            </a>
            .
          </p>
          <ol className="full-transcript-lines" lang="en">
            {lines.map((line) => (
              <li key={line.position}>
                <strong>{line.speaker}</strong>
                <span>{line.text_en}</span>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  )
}
