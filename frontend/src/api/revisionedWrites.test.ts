import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  missingRevisionFields, REVISION_FIELDS, REVISIONED_WRITES, revisionedWrite,
} from './revisionedWrites'

type Schema = { properties?: Record<string, unknown>; required?: string[] }
type Operation = {
  responses?: Record<string, unknown>
  requestBody?: { content?: Record<string, { schema?: { $ref?: string } }> }
}
type OpenApi = {
  paths: Record<string, Record<string, Operation>>
  components: { schemas: Record<string, Schema> }
}

// O Vitest roda com raiz em frontend/ (onde fica o vite.config.ts); o contrato
// é o mesmo arquivo que `npm run gen:api` e `check:api` leem.
const contract = JSON.parse(
  readFileSync(resolve(process.cwd(), '../backend/openapi.json'), 'utf8'),
) as OpenApi
const MUTABLE = ['post', 'put', 'patch', 'delete']

/**
 * O que o contrato exige: toda operação mutável cujo corpo JSON declara um dos
 * campos de revisão/idempotência (opcional ou não) e toda operação que
 * documenta 428. Quando o BE-44 publicar os 428 no OpenAPI, eles entram aqui
 * automaticamente e o registro precisa acompanhá-los.
 */
function fromContract(): { registry: Record<string, string[]>; with428: string[] } {
  const registry: Record<string, string[]> = {}
  const with428: string[] = []
  for (const [path, operations] of Object.entries(contract.paths)) {
    for (const [method, operation] of Object.entries(operations)) {
      if (!MUTABLE.includes(method)) continue
      const key = `${method.toUpperCase()} ${path}`
      const ref = operation.requestBody?.content?.['application/json']?.schema?.$ref
      const schema = ref ? contract.components.schemas[ref.split('/').pop() ?? ''] : undefined
      const fields = REVISION_FIELDS.filter((field) => schema?.properties && field in schema.properties)
      const documents428 = Object.keys(operation.responses ?? {}).includes('428')
      if (documents428) with428.push(key)
      if (fields.length > 0 || documents428) registry[key] = [...fields]
    }
  }
  return { registry, with428 }
}

const sorted = (record: Record<string, readonly string[]>) => Object.fromEntries(
  Object.entries(record).sort(([a], [b]) => a.localeCompare(b)).map(([key, fields]) => [key, [...fields].sort()]),
)

describe('registro das escritas revisionadas × backend/openapi.json', () => {
  const expected = fromContract()

  it('é exatamente o conjunto que o contrato declara, nos dois sentidos', () => {
    // Falha se um write novo com expected_revision/operation_key/idempotency_key
    // entrar no contrato sem ser registrado — ou se o registro inventar rota ou campo.
    expect(sorted(REVISIONED_WRITES)).toEqual(sorted(expected.registry))
  })

  it('toda operação que documenta 428 está no registro com pelo menos um campo', () => {
    for (const key of expected.with428) {
      expect(REVISIONED_WRITES, key).toHaveProperty(key)
      expect(REVISIONED_WRITES[key as keyof typeof REVISIONED_WRITES].length, key).toBeGreaterThan(0)
    }
  })

  it('cobre as quatro rotas que o backend já protege com require_revision', () => {
    expect(REVISIONED_WRITES['PUT /api/writing/prompts/{prompt_id}/draft']).toContain('expected_revision')
    expect(REVISIONED_WRITES['POST /api/writing/prompts/{prompt_id}/versions']).toContain('expected_revision')
    expect(REVISIONED_WRITES['PUT /api/courses/{course_slug}/lessons/{number}/study-session']).toContain('expected_revision')
    expect(REVISIONED_WRITES['POST /api/review/{item_id}/grade']).toEqual(
      expect.arrayContaining(['expected_revision', 'idempotency_key']),
    )
  })
})

describe('casamento de pedidos concretos com o registro', () => {
  it('resolve parâmetros de caminho e ignora método ou rota fora do registro', () => {
    expect(revisionedWrite('put', '/api/writing/prompts/4/draft')?.key).toBe('PUT /api/writing/prompts/{prompt_id}/draft')
    expect(revisionedWrite('PUT', '/api/courses/voa-level-1/lessons/31/study-session')?.fields).toEqual(['expected_revision'])
    expect(revisionedWrite('DELETE', '/api/me/account')?.fields).toEqual(['operation_key'])
    expect(revisionedWrite('GET', '/api/writing/prompts/4/draft')).toBeNull()
    expect(revisionedWrite('PUT', '/api/writing/prompts/4/draft/extra')).toBeNull()
    expect(revisionedWrite('PUT', '/api/writing/prompts//draft')).toBeNull()
    expect(revisionedWrite('PUT', '/api/me/study-plan')).toBeNull()
  })

  it('trata null, undefined e corpo não-objeto como campo ausente', () => {
    const fields = ['expected_revision', 'operation_key'] as const
    expect(missingRevisionFields(fields, { expected_revision: 0, operation_key: 'k' })).toEqual([])
    expect(missingRevisionFields(fields, { expected_revision: null, operation_key: 'k' })).toEqual(['expected_revision'])
    expect(missingRevisionFields(fields, { operation_key: undefined })).toEqual(['expected_revision', 'operation_key'])
    expect(missingRevisionFields(fields, null)).toEqual(['expected_revision', 'operation_key'])
    expect(missingRevisionFields(fields, [1])).toEqual(['expected_revision', 'operation_key'])
  })
})
