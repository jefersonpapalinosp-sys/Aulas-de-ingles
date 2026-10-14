import type { FullConfig } from '@playwright/test'
import { assertTarget, checkStack, readSentinel } from './safety.mjs'

export default async function globalSetup(config: FullConfig) {
  for (const project of config.projects) assertTarget(project.use.baseURL)
  try {
    await checkStack()
    readSentinel()
  } catch {
    throw new Error('E2E bloqueado antes dos testes: stack descartável não confirmada. Execute make e2e-up; não use dev/prod.')
  }
  return async () => {
    // Só consulta a base sentinela criada pelo init descartável; nunca a do aluno.
    readSentinel()
  }
}
