import { readLocal, writeLocal } from '../../storage/local'
import type { SelfRating } from './speakingUpload'

/** Autoavaliação do shadowing, guardada só neste navegador.
 *
 * A chave ganhou o curso na v2. A v1 não o tinha, então ela é lida como sendo
 * do `voa-level-1` — o único curso que existia quando ela foi escrita — e
 * migrada na primeira leitura. Sem isso, quem autoavaliou antes veria os
 * botões vazios e concluiria que o aplicativo perdeu o trabalho dele.
 */
export function selfRatingKey(userId: number, courseSlug: string, lessonNumber: number, cueId: number): string {
  return `aulas-ingles:shadowing-rating:v2:${userId}:${courseSlug}:${lessonNumber}:${cueId}`
}

export function readSelfRating(
  userId: number, courseSlug: string, lessonNumber: number, cueId: number,
): { rating: SelfRating | null; warning: string } {
  const key = selfRatingKey(userId, courseSlug, lessonNumber, cueId)
  const current = readLocal(key)
  let saved = current.ok ? current.value : null
  let warning = current.ok ? '' : current.error
  if (current.ok && !saved && courseSlug === 'voa-level-1') {
    const legacy = readLocal(`aulas-ingles:shadowing-rating:v1:${userId}:${lessonNumber}:${cueId}`)
    saved = legacy.ok ? legacy.value : null
    if (!legacy.ok) warning = legacy.error
    if (saved) {
      const copied = writeLocal(key, saved)
      if (!copied.ok) warning = copied.error
    }
  }
  const rating = saved === 'repeat' || saved === 'almost' || saved === 'confident' ? saved : null
  return { rating, warning }
}
