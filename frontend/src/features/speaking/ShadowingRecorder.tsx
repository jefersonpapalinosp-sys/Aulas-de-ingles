import type { SpeakingPolicy } from '../../api/client'
import type { SelfRating } from './speakingUpload'

const RATINGS = [
  ['repeat', 'Quero repetir'],
  ['almost', 'Quase lá'],
  ['confident', 'Confiante'],
] as const

export function ratingLabel(value: SelfRating): string {
  return value === 'repeat' ? 'Quero repetir' : value === 'almost' ? 'Quase lá' : 'Confiante'
}

/** A gravação desta tentativa: ouvir, autoavaliar, autorizar e enviar.
 *
 * O consentimento é por gravação e nunca fica marcado de saída — o padrão é a
 * gravação não sair do dispositivo. O botão de baixar está ao lado do de
 * enviar de propósito: é a saída quando o envio não é possível.
 */
export function ShadowingRecorder({
  recordingUrl, recordingBlob, policy, rating, consent, saving, saved, pending,
  onRating, onConsent, onSave, onDiscard,
}: {
  recordingUrl: string
  recordingBlob: Blob | null
  policy: SpeakingPolicy | undefined
  rating: SelfRating | null
  consent: boolean
  saving: boolean
  saved: boolean
  pending: boolean
  onRating: (value: SelfRating) => void
  onConsent: (value: boolean) => void
  onSave: () => void
  onDiscard: () => void
}) {
  const tipo = recordingBlob?.type.split(';')[0] ?? ''
  const grande = Boolean(recordingBlob && policy && recordingBlob.size > policy.max_bytes)
  const formatoRecusado = Boolean(recordingBlob && policy && !policy.mime_types.includes(tipo))
  return (
    <div className="shadowing-result">
      <div className="recording-preview">
        <p>3. Ouvir minha gravação</p>
        {/* Prévia privada: sem transcrição automática ou envio sem consentimento. */}
        {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
        <audio aria-label="Ouvir minha gravação" controls src={recordingUrl} preload="metadata" />
      </div>
      <fieldset>
        <legend>4. Como foi sua tentativa?</legend>
        {RATINGS.map(([value, label]) => (
          <button
            type="button"
            key={value}
            className={rating === value ? 'selected' : ''}
            aria-pressed={rating === value}
            disabled={saving || pending}
            onClick={() => onRating(value)}
          >
            {label}
          </button>
        ))}
      </fieldset>
      <label className="speaking-consent">
        <input
          type="checkbox"
          checked={consent}
          disabled={saving || saved}
          onChange={(event) => onConsent(event.target.checked)}
        />
        <span>
          Concordo em salvar esta gravação na minha conta. Posso excluí-la quando quiser.
        </span>
      </label>
      <div className="speaking-save-actions">
        <button
          type="button"
          className="btn"
          disabled={!recordingBlob || !consent || saving || saved || !policy || grande || formatoRecusado}
          onClick={onSave}
        >
          {saving ? 'Salvando…' : saved ? 'Gravação salva' : 'Salvar na minha conta'}
        </button>
        <button type="button" className="btn ghost" disabled={saving} onClick={onDiscard}>
          Descartar gravação local
        </button>
      </div>
      <a href={recordingUrl} download="minha-gravacao">Baixar gravação local</a>
      {recordingBlob && !saved && <p role="note">
        Gravação local — envio não confirmado. Ela não entra na fila de exercícios.
        Envie ou baixe antes de fechar a aba para não perder esta tentativa.
      </p>}
      {grande && policy && (
        <p className="shadowing-warning" role="alert">
          O arquivo excede {policy.max_bytes.toLocaleString('pt-BR')} bytes. Baixe a gravação ou faça uma tentativa mais curta.
        </p>
      )}
      {formatoRecusado && (
        <p role="alert">Este formato não pode ser enviado. Baixe a gravação ou use outro navegador.</p>
      )}
    </div>
  )
}
