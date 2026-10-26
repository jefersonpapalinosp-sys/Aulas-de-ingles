export class ApiError extends Error {
  readonly status?: number
  readonly requestId?: string
  readonly code?: string
  constructor(resource: string, response?: Response) {
    super(`Não foi possível carregar ${resource}.`)
    this.name = 'ApiError'
    this.status = response?.status
    const id = response?.headers?.get('x-request-id')
    // Só expor identificador curto, nunca headers/corpos de resposta completos.
    if (id && /^[\w.-]{1,128}$/.test(id)) this.requestId = id
    const code = response?.headers?.get('x-error-code')
    if (code && ['session_invalid', 'invalid_credentials', 'conflict', 'service_unavailable', 'revision_required', 'idempotency_key_required'].includes(code)) this.code = code
  }
}

export function errorGuidance(error: Error): { message: string; next: string } {
  if (!navigator.onLine) return { message: 'Você está sem conexão.', next: 'Reconecte-se. Não limpe os dados do navegador.' }
  const status = error instanceof ApiError ? error.status : undefined
  const code = error instanceof ApiError ? error.code : undefined
  // Os dois códigos do cutover (revisão e chave de idempotência) pedem a mesma
  // coisa do aluno: atualizar o aplicativo. O aviso é um só.
  if (status === 428 || code === 'revision_required' || code === 'idempotency_key_required') return { message: 'Esta versão do aplicativo precisa ser atualizada.', next: 'Rascunhos e fila local foram preservados. Use o aviso "Atualize o aplicativo" para recarregar quando estiver pronto.' }
  if (status === 409 || code === 'conflict') return { message: 'O estado desta atividade mudou.', next: 'Preserve sua resposta e confira o estado atual antes de enviar novamente.' }
  if (status === 503 || code === 'service_unavailable') return { message: 'O serviço está temporariamente indisponível.', next: 'Seu trabalho local não deve ser apagado. Aguarde e tente novamente.' }
  if (status === 404) return { message: 'Este conteúdo não está disponível.', next: 'Confira a aula ou volte ao catálogo.' }
  if (status === 401 || status === 403) return { message: 'Não foi possível autorizar este acesso.', next: 'Confira a sessão ou entre novamente na mesma conta.' }
  if (status === 429) return { message: 'Há muitas solicitações neste momento.', next: 'Aguarde antes de tentar novamente.' }
  return { message: 'Não foi possível carregar esta área agora.', next: 'Tente novamente. Se persistir, envie os detalhes técnicos ao suporte.' }
}
