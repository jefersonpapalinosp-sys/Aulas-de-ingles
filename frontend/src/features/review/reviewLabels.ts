import type { ReviewItemType } from '../../api/client'

/** Notas do SM-2 como o aluno as vê, com a tecla que as aciona.
 *
 * A tecla faz parte do rótulo de propósito: revisar com o teclado é o caminho
 * rápido, e esconder o atalho faria todo mundo usar o mouse.
 */
export const NOTES = [
  { key: '1', label: 'Errei', quality: 1, className: 'errei' },
  { key: '2', label: 'Difícil', quality: 3, className: 'dificil' },
  { key: '3', label: 'Bom', quality: 4, className: 'bom' },
  { key: '4', label: 'Fácil', quality: 5, className: 'facil' },
] as const

export const TYPE_LABELS: Record<ReviewItemType, string> = {
  vocabulary: 'Vocabulário',
  grammar_error: 'Erro gramatical',
  phrase: 'Frase',
  listening: 'Listening',
  writing_prompt: 'Escrita',
  speaking_prompt: 'Speaking',
}

export function inHowLong(days: number): string {
  if (days === 1) return 'amanhã'
  if (days < 30) return `em ${days} dias`
  if (days < 365) return `em ${Math.round(days / 30)} meses`
  return `em ${(days / 365).toFixed(1)} anos`
}

export function durationLabel(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  return `${Math.ceil(seconds / 60)} min`
}
