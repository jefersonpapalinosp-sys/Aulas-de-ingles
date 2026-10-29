import type { Rating, Turn } from './dialogueTransport'

const LABELS: Record<string, string> = {
  target_terms_missing: 'Vocabulário solicitado',
  grammar_pattern_missing: 'Padrão gramatical solicitado',
  too_short: 'Mínimo de três palavras', too_long: 'Até sessenta palavras',
}

function Coverage({ items, used, missing }: {
  items: { text: string; covered: boolean }[]; used: string; missing: string
}) {
  if (!items.length) return null
  return <>{[true, false].map(covered => <p key={String(covered)}>
    {covered ? used : missing}:{' '}
    {items.some(item => item.covered === covered)
      ? <span lang="en">{items.filter(item => item.covered === covered).map(item => item.text).join(', ')}</span>
      : 'nenhum'}.
  </p>)}</>
}

export function DialogueTurnView({ turn, guided, disabled, onRate, onSpeak }: {
  turn: Turn; guided: boolean; disabled: boolean
  onRate: (rating: Rating) => void; onSpeak: (text: string) => void
}) {
  return <li className="dialogue-turn">
    <h3>Turno {turn.position}</h3>
    {turn.state === 'pending' ? <p>Processamento na fila…</p> : turn.state === 'failed'
      ? <p role="alert">Não foi possível processar este turno. Você pode continuar por texto no próximo.</p> : <>
        <p>{turn.input_kind === 'audio' ? 'Transcrição automatizada da sua fala' : 'Você escreveu'}</p>
        <p lang="en" className="transcription-copy">{turn.words?.length ? turn.words.map((word, i) =>
          <span key={i} className={word.confidence < 0.75 ? 'low-confidence' : ''}>
            {word.text}{word.confidence < 0.75 && <small> (transcrição incerta)</small>}{' '}
          </span>) : turn.transcript ?? 'Texto removido conforme a retenção.'}</p>
        <ul>{Object.entries(turn.checks).map(([code, passed]) =>
          <li key={code}>{LABELS[code] ?? 'Critério da aula'}: {passed ? 'atendido' : 'a revisar'}.</li>)}</ul>
        {turn.check_details ? <>
          <Coverage items={turn.check_details.target_terms} used="Termos usados" missing="Termos não identificados" />
          <Coverage items={turn.check_details.grammar_patterns} used="Padrões identificados" missing="Padrões não identificados" />
        </> : <p>Detalhamento dos critérios indisponível para este turno.</p>}
        <p className="assist-label">{turn.fallback ? 'Resposta do roteiro · assistência indisponível'
          : guided ? 'Automatizado, em avaliação' : 'Resposta do roteiro da aula'}</p>
        <p lang="en" className="dialogue-partner">{turn.partner_text ?? 'Resposta removida conforme a retenção.'}</p>
        {turn.partner_text && <button type="button" disabled={disabled} onClick={() => onSpeak(turn.partner_text!)}>Ouvir resposta do turno {turn.position}</button>}
        {turn.hints.map((hint, i) => <p key={i}><strong>Dica automatizada · em avaliação:</strong> {hint.message}</p>)}
        {guided && <div role="group" aria-label={`Avaliar resposta do turno ${turn.position}`}>
          <button type="button" disabled={disabled} aria-pressed={turn.human_rating === 'helpful'} onClick={() => onRate('helpful')}>Foi útil</button>
          <button type="button" disabled={disabled} aria-pressed={turn.human_rating === 'not_helpful'} onClick={() => onRate('not_helpful')}>Não foi útil</button>
        </div>}
      </>}
  </li>
}
