import createClient from 'openapi-fetch'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { autenticacao, onSessaoPerdida, setAccessToken } from './client'
import type { paths } from './schema'

// O cliente real usa baseUrl vazio: no browser a URL relativa resolve contra
// a origem da página, mas o Request do Node não aceita. O teste monta um
// cliente com base absoluta e o MESMO middleware.
const api = createClient<paths>({
  baseUrl: 'http://localhost',
  credentials: 'same-origin',
  // Resolve o fetch na hora da chamada: o openapi-fetch captura o global na
  // criação do cliente, que acontece antes do stub de cada teste.
  fetch: (req) => globalThis.fetch(req),
})
api.use(autenticacao)

/**
 * O access token vive 15 minutos em memória. Antes deste middleware, passado
 * esse prazo toda escrita falhava com 401 e a interface seguia mostrando o
 * usuário logado — o progresso ficava preso no dispositivo.
 */

/** O middleware chama fetch ora com Request, ora com string. */
function caminhoDe(arg: unknown): string {
  const url = typeof arg === 'string' ? arg : (arg as Request).url
  return new URL(url, 'http://localhost').pathname
}

function resposta(status: number, corpo: unknown = {}) {
  return new Response(JSON.stringify(corpo), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  setAccessToken('token-velho')
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  onSessaoPerdida(null)
  setAccessToken(null)
  vi.unstubAllGlobals()
})

describe('renovação automática no 401', () => {
  it('renova e repete a requisição que falhou', async () => {
    fetchMock
      .mockResolvedValueOnce(resposta(401, { detail: 'Não autenticado.' }))
      .mockResolvedValueOnce(resposta(200, { access_token: 'token-novo' }))
      .mockResolvedValueOnce(resposta(200, []))

    const { response } = await api.GET('/api/lessons')

    expect(response.status).toBe(200)
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(caminhoDe(fetchMock.mock.calls[1]![0])).toBe('/api/auth/refresh')
    const retentativa = fetchMock.mock.calls[2]![0] as Request
    expect(retentativa.headers.get('Authorization')).toBe('Bearer token-novo')
  })

  it('avisa que a sessão acabou quando o refresh também falha', async () => {
    const perdeu = vi.fn()
    onSessaoPerdida(perdeu)
    fetchMock
      .mockResolvedValueOnce(resposta(401))
      .mockResolvedValueOnce(resposta(401, { detail: 'Sessão encerrada.' }))

    const { response } = await api.GET('/api/lessons')

    expect(response.status).toBe(401)
    expect(perdeu).toHaveBeenCalledTimes(1)
  })

  it('não entra em laço: cada requisição é retentada uma vez só', async () => {
    fetchMock
      .mockResolvedValueOnce(resposta(401))
      .mockResolvedValueOnce(resposta(200, { access_token: 'token-novo' }))
      .mockResolvedValueOnce(resposta(401))

    const { response } = await api.GET('/api/lessons')

    expect(response.status).toBe(401)
    // original, refresh e uma única retentativa
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('não tenta renovar a própria rota de autenticação', async () => {
    fetchMock.mockResolvedValueOnce(resposta(401, { detail: 'E-mail ou senha incorretos.' }))

    const { response } = await api.POST('/api/auth/login', {
      body: { email: 'x@y.com', password: 'senha-bem-grande' },
    })

    expect(response.status).toBe(401)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('várias chamadas simultâneas compartilham um único refresh', async () => {
    // O refresh rotaciona: usar um revoga o anterior. Sem o single-flight, a
    // segunda chamada invalidaria a sessão que a primeira acabou de renovar.
    fetchMock.mockImplementation(async (arg: unknown) => {
      if (caminhoDe(arg) === '/api/auth/refresh') {
        return resposta(200, { access_token: 'token-novo' })
      }
      const autorizacao = typeof arg === 'string' ? null : (arg as Request).headers.get('Authorization')
      return autorizacao === 'Bearer token-novo' ? resposta(200, []) : resposta(401)
    })

    const resultados = await Promise.all([
      api.GET('/api/lessons'),
      api.GET('/api/courses'),
      api.GET('/api/me/progress'),
    ])

    expect(resultados.every((r) => r.response.status === 200)).toBe(true)
    const refreshes = fetchMock.mock.calls.filter((c) => caminhoDe(c[0]) === '/api/auth/refresh')
    expect(refreshes).toHaveLength(1)
  })
})
