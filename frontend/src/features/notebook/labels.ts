import type { HistoricalEvidenceKind, NotebookKind } from '../../api/client'
import { ApiError } from '../../api/errors'

export const KINDS: readonly { value: NotebookKind; label: string }[] = [
  { value: 'note', label: 'Anotação livre' },
  { value: 'favorite_phrase', label: 'Frase favorita' },
  { value: 'personal_example', label: 'Exemplo pessoal' },
  { value: 'recurring_error', label: 'Erro recorrente' },
  { value: 'teacher_question', label: 'Pergunta ao professor' },
]

export const SHORT_DATE = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short' })
export const SHORT_DATE_TIME = new Intl.DateTimeFormat('pt-BR', {
  dateStyle: 'short',
  timeStyle: 'short',
})

export const HISTORY_LABELS: Record<HistoricalEvidenceKind, string> = {
  exercise: 'Exercício',
  practice: 'Prática guiada',
  writing: 'Correção de escrita',
  speaking: 'Tentativa de fala',
  checkpoint: 'Checkpoint',
}

export function kindLabel(kind: NotebookKind): string {
  return KINDS.find((item) => item.value === kind)?.label ?? kind
}

/**
 * Mensagem de falha do Caderno com o identificador da requisição quando a API
 * devolveu um: é por ele que o responsável acha a requisição no log, sem que o
 * aluno precise descrever o que aconteceu.
 */
export function failureMessage(error: unknown, fallback: string): string {
  const requestId = error instanceof ApiError ? error.requestId : undefined
  return requestId ? `${fallback} (requisição ${requestId})` : fallback
}
