import { readdirSync, readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { QueryClient } from '@tanstack/react-query'
import { afterEach, describe, expect, it } from 'vitest'
import { invalidateStudy, STUDY_INVALIDATIONS, type StudyEvent } from './invalidateStudy'

const client = new QueryClient({ defaultOptions: { queries: { staleTime: 300_000 } } })
afterEach(() => client.clear())

const events = Object.keys(STUDY_INVALIDATIONS) as StudyEvent[]
const scoped = events.filter((event) => STUDY_INVALIDATIONS[event].length > 0)
const prefixes = [...new Set(events.flatMap((event) => [...STUDY_INVALIDATIONS[event]])), 'lesson', 'courses']

describe('mapa único evento → chaves', () => {
  it.each(scoped)('%s invalida exatamente os prefixos do mapa, sem esperar o cache expirar', async (event) => {
    for (const key of prefixes) client.setQueryData([key, 'voa-level-1', 31], { old: true })
    await invalidateStudy(client, event)
    const expected: readonly string[] = STUDY_INVALIDATIONS[event]
    for (const key of prefixes) {
      expect(client.getQueryState([key, 'voa-level-1', 31])?.isInvalidated, key).toBe(expected.includes(key))
    }
  })

  it('uma tentativa de exercício alcança competências e a jornada da aula; a fila sincronizada, também as sessões de prática', () => {
    expect(STUDY_INVALIDATIONS.attempt).toEqual(expect.arrayContaining(
      ['progress', 'review', 'today', 'skills', 'study-session', 'course-completion'],
    ))
    expect(STUDY_INVALIDATIONS.queueSync).toEqual(expect.arrayContaining(
      [...STUDY_INVALIDATIONS.attempt, 'practice-session', 'practice-session-active'],
    ))
  })

  it('sessão reconfirmada invalida o cache inteiro, inclusive conteúdo de aula', async () => {
    client.setQueryData(['lesson', 'voa-level-1', 31], { old: true })
    client.setQueryData(['courses'], [])
    await invalidateStudy(client, 'sessionConfirmed')
    expect(client.getQueryState(['lesson', 'voa-level-1', 31])?.isInvalidated).toBe(true)
    expect(client.getQueryState(['courses'])?.isInvalidated).toBe(true)
  })

  it('nenhum código de produção chama invalidateQueries fora deste módulo', () => {
    // Critério de aceite FE-44: `grep -rn invalidateQueries src` só pode acusar este arquivo.
    const src = resolve(process.cwd(), 'src')
    const offenders = readdirSync(src, { recursive: true, encoding: 'utf8' })
      .filter((file) => /\.(ts|tsx)$/.test(file) && !/\.test\.tsx?$/.test(file) && file !== 'api/invalidateStudy.ts')
      .filter((file) => readFileSync(join(src, file), 'utf8').includes('invalidateQueries'))
    expect(offenders).toEqual([])
  })
})
