import type { WritingPrompt } from '../../api/client'
import type { DraftStatus } from './draftSync'

const MENSAGEM: Record<DraftStatus, string> = {
  idle: 'Pronto para escrever.',
  saving: 'Salvando…',
  saved: 'Rascunho salvo.',
  local: 'Salvo neste dispositivo; sincronização pendente.',
  unsaved: 'Texto apenas nesta tela; salvamento não confirmado. Não feche a página.',
}

function countWords(text: string): number {
  return text.match(/[A-Za-z]+(?:['’][A-Za-z]+)?/g)?.length ?? 0
}

function countSentences(text: string): number {
  return text.match(/[^.!?]+[.!?]+|[^.!?]+$/g)?.filter((part) => part.trim()).length ?? 0
}

/** O enunciado, o editor e o estado do salvamento.
 *
 * O estado fica junto do campo de propósito: é ali que o aluno olha antes de
 * fechar a página, e `unsaved` é a única mensagem que pede uma ação dele.
 */
export function WritingEditor({
  prompt, text, status, hydrated, recovered, storageWarning, onChange,
}: {
  prompt: WritingPrompt
  text: string
  status: DraftStatus
  hydrated: boolean
  recovered: boolean
  storageWarning: string
  onChange: (value: string) => void
}) {
  return (
    <>
      <p className="study-kicker">Writing · produção guiada</p>
      <h2 id="writing-title">{prompt.title}</h2>
      <p className="writing-instructions" lang="en">
        {prompt.instructions}
      </p>
      <ul className="writing-targets" aria-label="Critérios da atividade">
        <li>{prompt.min_words}+ palavras</li>
        <li>{prompt.min_sentences}+ frases</li>
        {prompt.requirements.map((requirement) => (
          <li key={requirement.label}>{requirement.label}</li>
        ))}
      </ul>

      <label className="writing-editor">
        <span>Seu texto em inglês</span>
        <textarea
          value={text}
          maxLength={5000}
          disabled={!hydrated}
          placeholder="Write your first sentence here…"
          onChange={(event) => onChange(event.target.value)}
        />
      </label>
      <div className="writing-meta">
        <span>{countWords(text)} palavras · {countSentences(text)} frases</span>
        <span role="status" className={status === 'local' || status === 'unsaved' ? 'failed' : ''}>
          {hydrated ? MENSAGEM[status] : 'Carregando rascunho…'}
        </span>
      </div>
      {storageWarning && <p role="alert" className="erro">{storageWarning}</p>}
      {recovered && <p>Rascunho recuperado neste dispositivo. Confira a sincronização com sua conta.</p>}
    </>
  )
}
