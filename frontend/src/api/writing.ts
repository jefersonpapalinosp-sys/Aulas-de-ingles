import { useEffect, useMemo, useSyncExternalStore } from 'react'
import { DraftConflict, DraftSync } from '../features/writing/draftSync'
import { api, type WritingDraft } from './client'
import { ApiError } from './errors'

/** Corpo do 409 verificado, não afirmado.
 *
 * Antes isto era um cast (`error as { detail?: { current?: WritingDraft } }`):
 * a forma vinha da rede e o TypeScript só acreditava. Se o campo mudasse de
 * nome, o conflito passaria a ser silencioso e o aluno perderia texto sem
 * nenhum aviso. O `ApiError` não carrega o corpo de propósito — ele expõe só
 * `status`, `code` e `request_id` —, então quem precisa do rascunho da conta
 * valida a forma aqui.
 */
export function conflictingDraft(body: unknown): WritingDraft | null {
  if (!body || typeof body !== 'object') return null
  const detail: unknown = (body as { detail?: unknown }).detail
  if (!detail || typeof detail !== 'object') return null
  const current: unknown = (detail as { current?: unknown }).current
  if (!current || typeof current !== 'object') return null
  const draft = current as WritingDraft
  return typeof draft.text === 'string' && Number.isInteger(draft.prompt_id) ? draft : null
}

export function useWritingDraftSync(promptId: number, userId: number) {
  const controller = useMemo(() => {
    const path = { params: { path: { prompt_id: promptId } } }
    async function read(): Promise<WritingDraft> {
      const { data, response } = await api.GET('/api/writing/prompts/{prompt_id}/draft', path)
      if (!data) throw new ApiError('o rascunho', response)
      return data
    }
    return new DraftSync(userId, promptId, {
      read,
      save: async (body) => {
        const { data, error, response } = await api.PUT('/api/writing/prompts/{prompt_id}/draft', { ...path, body })
        if (response?.status === 409) throw new DraftConflict(conflictingDraft(error) ?? (await read()))
        if (!data) throw new ApiError('o rascunho salvo', response)
        return data
      },
      createVersion: async (body) => {
        const { data, error, response } = await api.POST('/api/writing/prompts/{prompt_id}/versions', { ...path, body })
        if (response?.status === 409) throw new DraftConflict(conflictingDraft(error) ?? (await read()))
        if (!data) throw new ApiError('a versão criada', response)
        return data
      },
    })
  }, [promptId, userId])
  const state = useSyncExternalStore(controller.subscribe, controller.snapshot)
  useEffect(() => {
    void controller.hydrate()
    return () => { controller.dispose() }
  }, [controller])
  return { ...state, change: controller.change, flush: controller.flush,
    createVersion: controller.createVersion, resolve: controller.resolve }
}
