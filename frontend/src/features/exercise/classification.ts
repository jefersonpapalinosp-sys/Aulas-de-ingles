/** Resposta de classificação: mapa item→categoria, estável na ordem.
 *
 * A ordenação é o que torna a resposta comparável no servidor: dois alunos que
 * classificaram igual mandam a mesma string, independentemente da ordem em que
 * clicaram.
 */
export function classificationAnswer(items: string[], assignments: Record<string, string>): string {
  if (items.some((item) => !assignments[item])) return ''
  return JSON.stringify(
    Object.fromEntries([...items].sort().map((item) => [item, assignments[item]])),
  )
}

/** Lê um gabarito de classificação; `null` quando não é um mapa de strings. */
export function classificationEntries(answer: string): Array<[string, string]> | null {
  try {
    const value: unknown = JSON.parse(answer)
    if (!value || Array.isArray(value) || typeof value !== 'object') return null
    const entries = Object.entries(value)
    return entries.every((entry) => typeof entry[1] === 'string')
      ? (entries as Array<[string, string]>)
      : null
  } catch {
    return null
  }
}

export const SUPPORTED_ACTIVITY_TYPES = new Set([
  'gap_fill',
  'multiple_choice',
  'transformation',
  'reorder',
  'dictation',
  'classification',
])
