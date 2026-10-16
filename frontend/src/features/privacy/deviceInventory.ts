import { listLocal } from '../../storage/local'
import { getAttemptQueueStats } from '../offline/attemptQueue'
import { hasVoiceDraft } from '../speaking/voiceDraft'

export type DeviceInventory = {
  drafts: number | null; mediaCommands: number | null; activityEvents: number | null
  localCopies: number | null; pendingAnswers: number | null; blockedAnswers: number | null
  voiceDraft: boolean
}

/** Contagens apenas, sem ler textos de outra conta ou excluir/marcar como enviado. */
export async function inspectDevice(userId: number): Promise<DeviceInventory> {
  const count = (prefix: string, excludeRevision = false) => {
    const result = listLocal(`aulas-ingles:${prefix}:${userId}:`)
    return result.ok ? result.value.filter((key) => !excludeRevision || !key.endsWith(':revision')).length : null
  }
  const copies = ['study-progress:v1', 'study-progress:v2', 'shadowing-rating:v1',
    'shadowing-rating:v2', 'practice-position:v1', 'media-position:v1', 'media-position:v2'].map((p) => count(p))
  const queue = await getAttemptQueueStats(userId).catch(() => null)
  return {
    drafts: count('writing-draft:v1', true), mediaCommands: count('media-pending:v2'),
    activityEvents: count('activity-event:v1'),
    localCopies: copies.some((value) => value === null) ? null : copies.reduce<number>((a, b) => a + (b ?? 0), 0),
    pendingAnswers: queue?.pending ?? null, blockedAnswers: queue?.blocked ?? null,
    voiceDraft: hasVoiceDraft(userId),
  }
}
