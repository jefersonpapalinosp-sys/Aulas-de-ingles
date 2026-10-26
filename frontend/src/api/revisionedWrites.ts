import type { paths } from './schema'

/**
 * Cutover de 13/11/2026 (`LEGACY_WRITES_UNTIL`): a partir dessa data a API
 * responde 428 `revision_required` a escritas sem `expected_revision` — ou sem
 * `operation_key`/`idempotency_key` nas rotas idempotentes.
 *
 * Regra do registro: toda operação mutável cujo corpo JSON declara um desses
 * campos no backend/openapi.json entra aqui com os campos que o cliente precisa
 * enviar, mesmo quando o contrato ainda os marca como opcionais (fase "expand").
 * `revisionedWrites.test.ts` compara este mapa com o contrato nos dois sentidos
 * e também exige a presença de qualquer operação que documente 428.
 *
 * Três camadas usam o registro:
 * 1. `RevisionedPaths` torna os campos obrigatórios e não nulos no cliente
 *    tipado: `npm run typecheck` recusa um write novo sem o campo.
 * 2. `assertRevisionedWrite` confere o corpo em dev/teste, inclusive no
 *    `authenticatedFetch`, que o contrato não tipa.
 * 3. Em produção o cliente não bloqueia nada: a API decide e a interface trata
 *    o 428 com o aviso "Atualize o aplicativo" (`revisionRequired.ts`).
 */
export const REVISION_FIELDS = ['expected_revision', 'operation_key', 'idempotency_key'] as const
export type RevisionField = (typeof REVISION_FIELDS)[number]

export const REVISIONED_WRITES = {
  'POST /api/courses/{course_slug}/lessons/{number}/practice-sessions': ['idempotency_key'],
  'PUT /api/courses/{course_slug}/lessons/{number}/study-session': ['expected_revision'],
  'POST /api/courses/{course_slug}/units/{unit_slug}/review/attempts': ['idempotency_key'],
  'POST /api/exercises/{exercise_id}/attempt': ['idempotency_key'],
  'PUT /api/lessons/{number}/study-session': ['expected_revision'],
  'DELETE /api/me/account': ['operation_key'],
  'POST /api/me/activity/events': ['operation_key'],
  'PUT /api/media/{media_id}/position': ['expected_revision', 'operation_key'],
  'PUT /api/practice-sessions/{session_id}/position': ['expected_revision', 'idempotency_key'],
  'POST /api/review/{item_id}/grade': ['expected_revision', 'idempotency_key'],
  'PUT /api/writing/prompts/{prompt_id}/draft': ['expected_revision'],
  'POST /api/writing/prompts/{prompt_id}/feedback': ['operation_key'],
  'POST /api/writing/prompts/{prompt_id}/versions': ['expected_revision'],
} as const satisfies Record<string, readonly RevisionField[]>

type Registry = typeof REVISIONED_WRITES
export type RevisionedWriteKey = keyof Registry

type OperationKey<P, M> = `${Uppercase<M & string>} ${P & string}`
type FieldsOf<K> = K extends RevisionedWriteKey ? Registry[K][number] : never

/** Campos do registro deixam de ser opcionais/nulos; o resto do corpo não muda. */
type TightenBody<Body, Fields extends string> = Omit<Body, Fields> & {
  [K in Extract<keyof Body, Fields>]-?: NonNullable<Body[K]>
}

type TightenOperation<Operation, Fields extends string> = Operation extends {
  requestBody: { content: { 'application/json': infer Body } }
}
  ? Omit<Operation, 'requestBody'> & {
      requestBody: { content: { 'application/json': TightenBody<Body, Fields> } }
    }
  : Operation

/** `paths` gerado, com os corpos das escritas revisionadas apertados. */
export type RevisionedPaths = {
  [P in keyof paths]: {
    [M in keyof paths[P]]: OperationKey<P, M> extends RevisionedWriteKey
      ? TightenOperation<paths[P][M], FieldsOf<OperationKey<P, M>>>
      : paths[P][M]
  }
}

type Matcher = { key: RevisionedWriteKey; method: string; pattern: RegExp }

const matchers: Matcher[] = (Object.keys(REVISIONED_WRITES) as RevisionedWriteKey[]).map((key) => {
  const [method, template] = key.split(' ') as [string, string]
  const escaped = template.replace(/[.*+?^$()|[\]\\]/g, '\\$&').replace(/\{[^}]+\}/g, '[^/]+')
  return { key, method, pattern: new RegExp(`^${escaped}$`) }
})

/** Entrada do registro para um pedido concreto, ou `null` se a rota não é revisionada. */
export function revisionedWrite(method: string, pathname: string): {
  key: RevisionedWriteKey
  fields: readonly RevisionField[]
} | null {
  const upper = method.toUpperCase()
  const found = matchers.find((item) => item.method === upper && item.pattern.test(pathname))
  return found ? { key: found.key, fields: REVISIONED_WRITES[found.key] } : null
}

export function missingRevisionFields(fields: readonly RevisionField[], body: unknown): RevisionField[] {
  const record = body && typeof body === 'object' && !Array.isArray(body)
    ? (body as Record<string, unknown>)
    : {}
  return fields.filter((field) => record[field] === undefined || record[field] === null)
}

/**
 * Fora de produção, uma escrita revisionada sem o campo falha antes de sair do
 * navegador. Em produção nada é bloqueado: o servidor responde 428 e a interface
 * pede a atualização sem descartar rascunho nem fila.
 */
export async function assertRevisionedWrite(request: Request): Promise<void> {
  if (import.meta.env.PROD) return
  const entry = revisionedWrite(request.method, new URL(request.url).pathname)
  if (!entry) return
  let body: unknown = null
  try {
    body = await request.clone().json()
  } catch {
    body = null
  }
  const missing = missingRevisionFields(entry.fields, body)
  if (missing.length > 0) {
    throw new Error(
      `Escrita revisionada sem ${missing.join(' e ')}: ${entry.key}. `
      + 'Após 13/11/2026 a API responde 428; envie o campo exigido pelo contrato.',
    )
  }
}
