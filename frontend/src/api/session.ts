/** Estado em memória; nenhum token é persistido no dispositivo. */
export type EstadoSessao = 'valida' | 'expirada' | 'indisponivel' | 'offline'
export type Renovacao =
  | { estado: 'valida'; token: string }
  | { estado: Exclude<EstadoSessao, 'valida'> | 'substituida' }

let accessToken: string | null = null
let geracao = 0
let usuarioEsperado: number | null = null
let perfilNaoConfirmado = false
let aoPerderSessao: (() => void) | null = null
let aoMudarEstado: ((estado: EstadoSessao) => void) | null = null
let renovacaoEmCurso: { geracao: number; promessa: Promise<Renovacao> } | null = null

export function setAccessToken(token: string | null): void {
  accessToken = token
  geracao += 1
}

export function setSessionUser(id: number | null): void {
  usuarioEsperado = id
}

/** Um perfil local não autoriza envio: /me deve confirmar a conta primeiro. */
export function setSessionReadOnly(value: boolean): void {
  perfilNaoConfirmado = value
}

export function sessionSnapshot() {
  return { token: accessToken, geracao, perfilNaoConfirmado, usuarioId: usuarioEsperado }
}

export function onSessaoPerdida(callback: (() => void) | null): void {
  aoPerderSessao = callback
}

export function onEstadoSessao(callback: ((estado: EstadoSessao) => void) | null): void {
  aoMudarEstado = callback
}

export function estadoIndisponivel(): 'offline' | 'indisponivel' {
  return navigator.onLine ? 'indisponivel' : 'offline'
}

export function encerrarSessao(expectedGeneration: number): void {
  if (geracao !== expectedGeneration) return
  setAccessToken(null)
  usuarioEsperado = null
  perfilNaoConfirmado = true
  aoMudarEstado?.('expirada')
  aoPerderSessao?.()
}

/** Bootstrap, JSON e áudio compartilham a mesma rotação de cookie nesta aba. */
export function renovarSessao(): Promise<Renovacao> {
  if (renovacaoEmCurso?.geracao === geracao) return renovacaoEmCurso.promessa
  const inicio = geracao
  const esperado = usuarioEsperado
  const atual = () => inicio === geracao
  const indisponivel = (): Renovacao => {
    const estado = estadoIndisponivel()
    aoMudarEstado?.(estado)
    return { estado }
  }
  const promessa = (async (): Promise<Renovacao> => {
    try {
      const response = await fetch('/api/auth/refresh', {
        method: 'POST', credentials: 'same-origin',
      })
      if (!atual()) return { estado: 'substituida' }
      // Somente 401 é revogação no contrato atual. 429/5xx/rede não são logout.
      if (response.status === 401) {
        encerrarSessao(inicio)
        return { estado: 'expirada' }
      }
      if (!response.ok) return indisponivel()
      const body: unknown = await response.json()
      if (!atual()) return { estado: 'substituida' }
      const token = body && typeof body === 'object' && 'access_token' in body
        ? body.access_token : null
      if (typeof token !== 'string' || !token.trim()) return indisponivel()

      // Outra aba pode ter trocado a conta do cookie. Nunca repetir uma escrita
      // da conta A com o token da conta B, nem confiar só no perfil em storage.
      if (esperado !== null) {
        const profileResponse = await fetch('/api/auth/me', {
          headers: { Authorization: `Bearer ${token}` }, credentials: 'same-origin',
        })
        if (!atual()) return { estado: 'substituida' }
        if (profileResponse.status === 401) {
          encerrarSessao(inicio)
          return { estado: 'expirada' }
        }
        if (!profileResponse.ok) return indisponivel()
        const profile: unknown = await profileResponse.json()
        if (!atual()) return { estado: 'substituida' }
        if (!profile || typeof profile !== 'object' || !('id' in profile)
          || typeof profile.id !== 'number') return indisponivel()
        if (profile.id !== esperado) {
          encerrarSessao(inicio)
          return { estado: 'expirada' }
        }
      }
      accessToken = token
      aoMudarEstado?.('valida')
      return { estado: 'valida', token }
    } catch {
      return atual() ? indisponivel() : { estado: 'substituida' }
    }
  })()
  const voo = { geracao: inicio, promessa }
  renovacaoEmCurso = voo
  void promessa.finally(() => {
    if (renovacaoEmCurso === voo) renovacaoEmCurso = null
  })
  return promessa
}
