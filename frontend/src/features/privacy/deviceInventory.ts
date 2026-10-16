import { listLocal, removeLocal } from '../../storage/local'
import { deleteAttemptQueueForUser, getAttemptQueueStats } from '../offline/attemptQueue'
import { clearVoiceDraftForUser, hasVoiceDraft } from '../speaking/voiceDraft'

const PRIVATE_PREFIXES = [
  'writing-draft:v1', 'media-pending:v2', 'activity-event:v1',
  'study-progress:v1', 'study-progress:v2', 'shadowing-rating:v1',
  'shadowing-rating:v2', 'practice-position:v1', 'media-position:v1',
  'media-position:v2',
]

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

/** Remove somente o namespace da conta informada; fontes legadas compartilhadas
 * ficam preservadas e um tombstone impede que elas restaurem respostas antigas. */
export async function clearDeviceData(userId: number): Promise<number> {
  await deleteAttemptQueueForUser(userId)
  const groups = PRIVATE_PREFIXES.map((prefix) => listLocal(`aulas-ingles:${prefix}:${userId}:`))
  const failed = groups.find((result) => !result.ok)
  if (failed && !failed.ok) throw new Error(failed.error)
  const keys = groups.flatMap((result) => result.ok ? result.value : [])
  for (const key of keys) {
    const result = removeLocal(key)
    if (!result.ok) throw new Error(result.error)
  }
  return keys.length + Number(clearVoiceDraftForUser(userId))
}
