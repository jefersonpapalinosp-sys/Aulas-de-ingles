/** Só memória desta aba, um envio por vez, cinco minutos; nunca storage ou envio automático. */
type VoiceDraft = { key: string; blob: Blob; duration: number; attemptId: number | null }
let draft: VoiceDraft | null = null
let timer: ReturnType<typeof setTimeout> | null = null

/** Observação sem consumir a gravação de recuperação, restrita à conta atual. */
export function hasVoiceDraft(userId: number): boolean {
  return draft?.key.startsWith(`${userId}:`) ?? false
}

export function clearVoiceDraft(key: string, expected?: VoiceDraft) {
  if (draft?.key !== key || (expected && draft !== expected)) return
  draft = null
  if (timer !== null) clearTimeout(timer)
  timer = null
}

export function retainVoiceDraft(value: VoiceDraft) {
  if (draft) clearVoiceDraft(draft.key)
  draft = value
  timer = setTimeout(() => clearVoiceDraft(value.key), 5 * 60_000)
}

export function takeVoiceDraft(key: string) {
  const value = draft?.key === key ? draft : null
  if (draft) clearVoiceDraft(draft.key) // Outra conta/contexto não herda o áudio.
  return value
}
