import { api, authenticatedFetch } from '../../api/client'
import type { components } from '../../api/schema'
import { sessionSnapshot } from '../../api/session'

export type Dialogue = components['schemas']['DialogueOut']
export type Turn = components['schemas']['DialogueTurnOut']
export type DialogueStatus = components['schemas']['DialogueStatusOut']
export type Mode = 'script' | 'guided'
export type Rating = 'helpful' | 'not_helpful'
export type Creation = { lesson_id: number; mode: Mode; partner_speaker: string | null; operation_key: string }
export type TextInput = { text: string; idempotency_key: string }

export class DialogueError extends Error {
  constructor(readonly status: number, readonly code = '') { super(code || `HTTP ${status}`) }
}

function unwrap<T>(result: { data?: T; response: Response; error?: unknown }): T {
  if (result.data !== undefined) return result.data
  const detail = result.error && typeof result.error === 'object' && 'detail' in result.error ? result.error.detail : null
  const code = detail && typeof detail === 'object' && 'code' in detail ? String(detail.code) : ''
  throw new DialogueError(result.response.status, code)
}

export interface DialogueTransport {
  session: typeof sessionSnapshot
  create: (body: Creation, signal: AbortSignal) => Promise<Dialogue>
  read: (id: number, signal: AbortSignal) => Promise<Dialogue>
  text: (id: number, position: number, body: TextInput, signal: AbortSignal) => Promise<unknown>
  audio: (id: number, position: number, blob: Blob, signal: AbortSignal) => Promise<unknown>
  rate: (id: number, position: number, rating: Rating, signal: AbortSignal) => Promise<unknown>
  remove: (id: number, signal: AbortSignal) => Promise<void>
}

export const dialogueTransport: DialogueTransport = {
  session: sessionSnapshot,
  create: async (body, signal) => unwrap(await api.POST('/api/speaking/dialogues', { body, signal })),
  read: async (dialogue_id, signal) => unwrap(await api.GET('/api/speaking/dialogues/{dialogue_id}', { params: { path: { dialogue_id } }, signal })),
  text: async (dialogue_id, position, body, signal) => unwrap(await api.POST('/api/speaking/dialogues/{dialogue_id}/turns/{position}/text', { params: { path: { dialogue_id, position } }, body, signal })),
  audio: async (id, position, blob, signal) => {
    const response = await authenticatedFetch(`/api/speaking/dialogues/${id}/turns/${position}/audio`, {
      method: 'PUT', signal, body: blob,
      headers: { 'Content-Type': blob.type, 'X-Audio-Consent': 'true' },
    })
    if (!response.ok) throw new DialogueError(response.status)
    return response.json()
  },
  rate: async (dialogue_id, position, rating, signal) => unwrap(await api.PUT('/api/speaking/dialogues/{dialogue_id}/turns/{position}/rating', { params: { path: { dialogue_id, position } }, body: { rating }, signal })),
  remove: async (dialogue_id, signal) => {
    const result = await api.DELETE('/api/speaking/dialogues/{dialogue_id}', { params: { path: { dialogue_id } }, signal })
    if (!result.response.ok && result.response.status !== 404) throw new DialogueError(result.response.status)
  },
}

export function dialogueError(error: unknown): string {
  if (error instanceof DialogueError) {
    if (error.status === 429) return 'Limite de envios atingido. Aguarde ou inicie uma conversa no Roteiro por texto.'
    if (error.code === 'assist_disabled') return 'O modo Guiado está indisponível. Você pode iniciar o Roteiro por texto.'
    if (error.code === 'dialogue_turn_limit') return 'Esta conversa chegou ao limite de turnos.'
    if (error.status === 401 || error.status === 403) return 'Confirme a sessão da mesma conta para continuar.'
    if (error.status === 413) return 'Áudio maior que o limite. Grave um trecho mais curto.'
    if (error.status === 415 || error.status === 422) return 'Entrada inválida. Confira o texto ou grave um áudio mais curto no formato permitido.'
    if (error.status === 409) return 'Esta posição já foi utilizada. Atualize a conversa antes de continuar.'
    if (error.status === 404) return 'Esta conversa não está mais disponível.'
  }
  return 'Não foi possível confirmar a operação. Sua entrada continua nesta tela. Tente novamente.'
}
