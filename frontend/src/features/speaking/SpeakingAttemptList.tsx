import type { AssistStatus, SpeakingAttempt } from '../../api/client'
import { useSpeakingHistory } from '../../api/speaking'
import { AssistQuota } from '../assist/AssistQuota'
import { ratingLabel } from './ShadowingRecorder'

const QUEBRADO = ['missing', 'changed']

/** Resultado da transcrição automatizada, sempre rotulado como automático. */
function TranscriptionResult({
  transcription, onRate, onDelete,
}: {
  transcription: NonNullable<SpeakingAttempt['transcription']>
  onRate: (jobId: number, rating: 'helpful' | 'not_helpful') => void
  onDelete: (jobId: number) => void
}) {
  return (
    <div className={`transcription-result ${transcription.status}`}>
      <p className="assist-label">Automatizado · somente avaliação</p>
      {transcription.status === 'queued' && (
        <p role="status">
          {transcription.attempt_count === 0
            ? 'Transcrição aguardando processamento…'
            : `O provedor não respondeu. Nova tentativa será feita automaticamente (${transcription.attempt_count} de ${transcription.max_attempts} realizadas).`}
        </p>
      )}
      {transcription.status === 'processing' && (
        <p role="status">
          Transcrição em processamento · tentativa{' '}
          {transcription.attempt_count} de {transcription.max_attempts}.
        </p>
      )}
      {transcription.status === 'failed' && (
        <p role="alert">
          A transcrição falhou após {transcription.attempt_count}{' '}
          {transcription.attempt_count === 1 ? 'tentativa' : 'tentativas'}.
          A gravação e sua autoavaliação não foram perdidas.
        </p>
      )}
      {transcription.status === 'completed' && (
        <>
          <p className="transcription-copy" lang="en">
            {transcription.words.map((word, index) => (
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
            Confiança média {Math.round((transcription.mean_confidence ?? 0) * 100)}% ·
            semelhança com a frase {Math.round((transcription.similarity_score ?? 0) * 100)}%
          </p>
          {transcription.low_confidence && (
            <p className="assist-warning" role="alert">
              Baixa confiança: ouça sua gravação e não trate esta transcrição como
              correção definitiva.
            </p>
          )}
          <div className="assist-rating" aria-label="Avaliar transcrição automática">
            <span>Este resultado ajudou?</span>
            <button type="button" aria-pressed={transcription.human_rating === 'helpful'}
              onClick={() => onRate(transcription.id, 'helpful')}>
              Sim
            </button>
            <button type="button" aria-pressed={transcription.human_rating === 'not_helpful'}
              onClick={() => onRate(transcription.id, 'not_helpful')}>
              Não
            </button>
          </div>
        </>
      )}
      <button type="button" className="assist-delete" onClick={() => onDelete(transcription.id)}>
        Excluir transcrição
      </button>
    </div>
  )
}

/** Gravações já salvas na conta desta aula.
 *
 * Integridade e conteúdo histórico aparecem como aviso em vez de esconder a
 * linha: o aluno praticou, e o histórico dele não desaparece porque o arquivo
 * ou o texto original mudou.
 */
export function SpeakingAttemptList({
  userId, courseSlug, lessonNumber, assist, announce,
}: {
  userId: number
  courseSlug: string
  lessonNumber: number
  assist: AssistStatus | undefined
  announce: (message: string) => void
}) {
  const history = useSpeakingHistory(userId, courseSlug, lessonNumber, announce)
  const attempts = history.query.data
  return (
    <div className="speaking-history">
      <h3>Gravações salvas nesta aula</h3>
      {assist && !assist.transcription_enabled && (
        <p>
          Transcrição automática está desativada. Ouvir, comparar e autoavaliar continuam
          disponíveis normalmente.
        </p>
      )}
      {assist?.transcription_enabled && (
        <p className="assist-disclosure">
          Recurso experimental: a transcrição é automatizada, pode errar e expira em{' '}
          {assist.retention_days} dias.
        </p>
      )}
      {assist?.transcription_enabled && <AssistQuota status={assist} />}
      {history.query.isPending && <p>Carregando histórico…</p>}
      {history.query.isError && <p>Não foi possível carregar o histórico.</p>}
      {attempts?.length === 0 && <p>Nenhuma gravação salva.</p>}
      {attempts && attempts.length > 0 && (
        <ul>
          {attempts.map((attempt) => {
            const quebrado = QUEBRADO.includes(attempt.integrity_state ?? '')
            return (
              <li key={attempt.id}>
                <div>
                  {attempt.cue_text
                    ? <strong lang="en">{attempt.cue_text}</strong>
                    : <strong>Texto original indisponível</strong>}
                  <small>
                    {new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' })
                      .format(new Date(attempt.created_at))}
                    {attempt.self_rating ? ` · ${ratingLabel(attempt.self_rating)}` : ''}
                  </small>
                </div>
                <button type="button" disabled={quebrado} onClick={() => void history.play(attempt)}>Ouvir</button>
                {quebrado && (
                  <p role="status">Arquivo ausente ou alterado. O histórico foi preservado; grave uma nova tentativa ou solicite restauração de uma cópia conferida.</p>
                )}
                {attempt.historical_content_status === 'unavailable' && (
                  <p role="status">Sem texto original: ouça o áudio, sem comparação automática.</p>
                )}
                <button type="button" onClick={() => void history.remove(attempt.id)}>Excluir</button>
                {assist?.transcription_enabled && !attempt.transcription
                  && attempt.historical_content_status === 'available' && !quebrado && (
                  <button type="button" className="transcription-request" onClick={() => void history.transcribe(attempt.id)}>
                    Transcrever (experimental)
                  </button>
                )}
                {attempt.transcription && (
                  <TranscriptionResult
                    transcription={attempt.transcription}
                    onRate={(jobId, rating) => void history.rateTranscription(jobId, rating)}
                    onDelete={(jobId) => void history.removeTranscription(jobId)}
                  />
                )}
              </li>
            )
          })}
        </ul>
      )}
      {history.savedAudioUrl && history.playingAttemptId !== null && (
        // Gravação privada; não inventar legenda nem enviar para transcrição automaticamente.
        // eslint-disable-next-line jsx-a11y/media-has-caption
        <audio aria-label="Reprodução da gravação salva" controls autoPlay src={history.savedAudioUrl} />
      )}
    </div>
  )
}
