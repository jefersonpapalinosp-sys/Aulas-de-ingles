/**
 * Sinal único de "esta versão do cliente ficou para trás": a API respondeu 428
 * a alguma escrita — `revision_required` ou `idempotency_key_required`, que
 * pedem a mesma coisa do aluno. Fica em memória, sem token nem corpo
 * de resposta, e só é limpo ao recarregar a aplicação.
 */
let required = false
const listeners = new Set<() => void>()

function notify(): void {
  listeners.forEach((listener) => listener())
}

export function markRevisionRequired(): void {
  if (required) return
  required = true
  notify()
}

/** Exclusivo dos testes: a interface real só sai desse estado ao recarregar. */
export function resetRevisionRequired(): void {
  if (!required) return
  required = false
  notify()
}

export const revisionRequiredSnapshot = (): boolean => required

export function subscribeRevisionRequired(listener: () => void): () => void {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

export function isRevisionRequired(response: Response): boolean {
  return response.status === 428
}
