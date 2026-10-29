import { useState } from 'react'
import type { WritingDraft } from '../../api/client'

/** Duas versões do rascunho, e nenhuma escolha feita pelo aplicativo.
 *
 * O botão de copiar os dois existe porque a escolha é destrutiva para um dos
 * textos: antes de decidir, o aluno tem de poder levar os dois embora.
 */
export function DraftConflictPanel({
  conflict, text, onResolve,
}: {
  conflict: WritingDraft
  text: string
  onResolve: (useRemote: boolean) => void
}) {
  const [bothTexts, setBothTexts] = useState('')
  return (
    <section className="writing-conflict" aria-labelledby="draft-conflict-title">
      <div role="alert"><h3 id="draft-conflict-title">Há duas versões do rascunho</h3></div>
      <p>O texto do editor continua neste dispositivo. A conta possui a revisão {conflict.revision ?? 0},
        salva em {conflict.updated_at ? new Date(conflict.updated_at).toLocaleString() : 'data não informada'}.</p>
      <label>Texto salvo na conta<textarea readOnly value={conflict.text} /></label>
      <div className="writing-actions">
        <button type="button" onClick={() => onResolve(false)}>Manter meu texto</button>
        <button type="button" onClick={() => onResolve(true)}>Usar texto da conta</button>
        <button type="button" onClick={() => setBothTexts(`Neste dispositivo:\n${text}\n\nNa conta:\n${conflict.text}`)}>Preparar cópia dos dois</button>
      </div>
      {bothTexts && <label>Selecione e copie os dois textos<textarea readOnly value={bothTexts} onFocus={(event) => event.target.select()} /></label>}
    </section>
  )
}
