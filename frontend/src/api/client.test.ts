import createClient from 'openapi-fetch'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  autenticacao, authenticatedFetch, onEstadoSessao, onSessaoPerdida,
  renovarSessao, setAccessToken, setSessionReadOnly, setSessionUser,
} from './client'
import { resetRevisionRequired, revisionRequiredSnapshot } from './revisionRequired'
import { sessionSnapshot } from './session'
import type { paths } from './schema'

// O cliente real usa baseUrl vazio: no browser a URL relativa resolve contra
// a origem da página, mas o Request do Node não aceita. O teste monta um
// cliente com base absoluta e o MESMO middleware. Fica tipado com `paths` cru
// (não `RevisionedPaths`) de propósito: assim dá para exercitar o guard em
// runtime com corpos que o cliente de produção nem compilaria.
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

let fetchMock: ReturnType<typeof vi.fn<(input: Request | string) => Promise<Response>>>

beforeEach(() => {
  setAccessToken('token-velho')
  setSessionReadOnly(false)
  setSessionUser(null)
  fetchMock = vi.fn<(input: Request | string) => Promise<Response>>()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  onSessaoPerdida(null)
  onEstadoSessao(null)
  setAccessToken(null)
  resetRevisionRequired()
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
    const perdeu = vi.fn()
    onSessaoPerdida(perdeu)
    fetchMock
      .mockResolvedValueOnce(resposta(401))
      .mockResolvedValueOnce(resposta(200, { access_token: 'token-novo' }))
      .mockResolvedValueOnce(resposta(401))

    const { response } = await api.GET('/api/lessons')

    expect(response.status).toBe(401)
    // original, refresh e uma única retentativa
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(perdeu).toHaveBeenCalledTimes(1)
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
    fetchMock.mockImplementation((arg: unknown) => {
      if (caminhoDe(arg) === '/api/auth/refresh') {
        return Promise.resolve(resposta(200, { access_token: 'token-novo' }))
      }
      const autorizacao = typeof arg === 'string' ? null : (arg as Request).headers.get('Authorization')
      return Promise.resolve(autorizacao === 'Bearer token-novo' ? resposta(200, []) : resposta(401))
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

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

describe('corpos realmente consumidos e transporte binário', () => {
  it.each(['POST', 'PUT'] as const)('reproduz %s sem perder conteúdo, headers ou idempotência', async (method) => {
    const bodies: string[] = []
    const requests: Request[] = []
    fetchMock.mockImplementation(async (input: Request | string) => {
      if (caminhoDe(input) === '/api/auth/refresh') return resposta(200, { access_token: 'novo' })
      const req = input as Request
      requests.push(req)
      bodies.push(await req.text()) // NÃO clone: simula o consumo real do fetch.
      expect(req.bodyUsed).toBe(true)
      return requests.length === 1 ? resposta(401) : resposta(200, {})
    })
    const result = method === 'POST'
      ? await api.POST('/api/exercises/{exercise_id}/attempt', {
        params: { path: { exercise_id: 31 } },
        headers: { 'X-Request-Id': 'pedido-31' },
        body: { answer: 'better', idempotency_key: 'mesma-chave', practice_session_id: 2 },
      })
      : await api.PUT('/api/writing/prompts/{prompt_id}/draft', {
        params: { path: { prompt_id: 31 } }, headers: { 'X-Request-Id': 'pedido-31' },
        body: { text: 'I study English every day.', expected_revision: 3 },
      })
    expect(result.response.status).toBe(200)
    expect(bodies).toHaveLength(2)
    expect(bodies[1]).toBe(bodies[0])
    if (method === 'POST') expect((JSON.parse(bodies[1]!) as { idempotency_key: string }).idempotency_key).toBe('mesma-chave')
    expect(requests[1]!.method).toBe(method)
    expect(requests[1]!.headers.get('X-Request-Id')).toBe('pedido-31')
    expect(requests[1]!.headers.get('Content-Type')).toBe('application/json')
    expect(requests[1]!.headers.get('Authorization')).toBe('Bearer novo')
    expect(requests[1]!.credentials).toBe('same-origin')
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('reenvia os mesmos bytes de Blob após o upload receber 401', async () => {
    // Blob nativo do Node é compatível com seu Request; jsdom tem outro Blob.
    const { Blob } = await import('node:buffer')
    const bytes = new Uint8Array([0, 255, 1, 2, 128])
    const recebidos: number[][] = []
    fetchMock.mockImplementation(async (input: Request | string) => {
      if (caminhoDe(input) === '/api/auth/refresh') return resposta(200, { access_token: 'novo' })
      const req = input as Request
      recebidos.push([...new Uint8Array(await req.arrayBuffer())])
      expect(req.headers.get('Content-Type')).toBe('audio/webm')
      return recebidos.length === 1 ? resposta(401) : resposta(200)
    })
    const response = await authenticatedFetch('/api/speaking/attempts/1/audio', {
      method: 'PUT', headers: { 'Content-Type': 'audio/webm' }, body: new Blob([bytes]) as unknown as globalThis.Blob,
    })
    expect(response.status).toBe(200)
    expect(recebidos).toEqual([[...bytes], [...bytes]])
  })

  it('renova também o download de dados privados', async () => {
    fetchMock.mockResolvedValueOnce(resposta(401))
      .mockResolvedValueOnce(resposta(200, { access_token: 'novo' }))
      .mockResolvedValueOnce(new Response(new Uint8Array([1, 2, 3])))
    const response = await authenticatedFetch('/api/me/export')
    expect([...new Uint8Array(await response.arrayBuffer())]).toEqual([1, 2, 3])
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('não copia nem repete ReadableStream', async () => {
    const body = new ReadableStream({ start(controller) { controller.enqueue(new Uint8Array([7])); controller.close() } })
    fetchMock.mockImplementation(async (input: Request | string) => {
      const req = new Request(input)
      expect([...new Uint8Array(await req.arrayBuffer())]).toEqual([7])
      return resposta(401)
    })
    const init: RequestInit & { duplex: string } = { method: 'PUT', body, duplex: 'half' }
    expect((await authenticatedFetch('/api/speaking/attempts/1/audio', init)).status).toBe(401)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('não envia credenciais para outra origem', async () => {
    await expect(authenticatedFetch('https://example.com/api/export')).rejects.toThrow('apenas a API')
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('indisponibilidade não é revogação', () => {
  it.each([429, 500, 502, 503])('mantém sessão no refresh %s sem repetir a escrita', async (status) => {
    const perdeu = vi.fn()
    const estado = vi.fn()
    onSessaoPerdida(perdeu)
    onEstadoSessao(estado)
    fetchMock.mockResolvedValueOnce(resposta(401)).mockResolvedValueOnce(resposta(status))
    const result = await api.GET('/api/me/progress')
    expect(result.response.status).toBe(503)
    expect(result.response.headers.get('X-Session-State')).toBe('indisponivel')
    expect(estado).toHaveBeenCalledWith('indisponivel')
    expect(perdeu).not.toHaveBeenCalled()
    expect(sessionSnapshot().token).toBe('token-velho')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it.each([null, {}, { access_token: '' }, { access_token: 17 }])('não trata token inválido como logout: %j', async (body) => {
    const perdeu = vi.fn()
    onSessaoPerdida(perdeu)
    fetchMock.mockResolvedValueOnce(resposta(401)).mockResolvedValueOnce(resposta(200, body))
    expect((await api.GET('/api/me/progress')).response.status).toBe(503)
    expect(perdeu).not.toHaveBeenCalled()
  })

  it('falha de rede e JSON inválido no refresh não encerram a sessão', async () => {
    const perdeu = vi.fn()
    onSessaoPerdida(perdeu)
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    expect((await renovarSessao()).estado).toBe('indisponivel')
    fetchMock.mockResolvedValueOnce(new Response('não é JSON', { status: 200 }))
    expect((await renovarSessao()).estado).toBe('indisponivel')
    expect(perdeu).not.toHaveBeenCalled()
  })

  it('não repete 403 nem 5xx da operação original', async () => {
    for (const status of [403, 500, 503]) {
      fetchMock.mockResolvedValueOnce(resposta(status))
      expect((await api.GET('/api/me/progress')).response.status).toBe(status)
    }
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('não reenvia automaticamente uma escrita cuja resposta se perdeu', async () => {
    fetchMock.mockImplementationOnce(async (input: Request | string) => {
      const req = new Request(input)
      await req.text()
      throw new TypeError('Connection lost after commit')
    })
    await expect(api.POST('/api/exercises/{exercise_id}/attempt', {
      params: { path: { exercise_id: 1 } }, body: { answer: 'better', idempotency_key: 'same' },
    })).rejects.toThrow('Connection lost')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})

describe('concorrência e conta proprietária', () => {
  it('compartilha refresh entre bootstrap, JSON e áudio', async () => {
    const refresh = deferred<Response>()
    fetchMock.mockImplementation(async (input: Request | string) => {
      if (caminhoDe(input) === '/api/auth/refresh') return refresh.promise
      return (input as Request).headers.get('Authorization') === 'Bearer novo' ? resposta(200) : resposta(401)
    })
    const boot = renovarSessao()
    const json = api.GET('/api/me/progress')
    const audio = authenticatedFetch('/api/speaking/attempts/1/audio')
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
    refresh.resolve(resposta(200, { access_token: 'novo' }))
    expect((await boot).estado).toBe('valida')
    expect((await json).response.status).toBe(200)
    expect((await audio).status).toBe(200)
    expect(fetchMock.mock.calls.filter((call) => caminhoDe(call[0]) === '/api/auth/refresh')).toHaveLength(1)
  })

  it('401 tardio usa o token já renovado sem rotacionar o cookie outra vez', async () => {
    const atrasada = deferred<Response>()
    fetchMock.mockImplementation(async (input: Request | string) => {
      if (caminhoDe(input) === '/api/auth/refresh') return resposta(200, { access_token: 'novo' })
      if ((input as Request).headers.get('Authorization') === 'Bearer novo') return resposta(200)
      if (caminhoDe(input) === '/api/me/progress') return atrasada.promise
      return resposta(401)
    })
    const lenta = api.GET('/api/me/progress')
    await api.GET('/api/lessons')
    atrasada.resolve(resposta(401))
    expect((await lenta).response.status).toBe(200)
    expect(fetchMock.mock.calls.filter((call) => caminhoDe(call[0]) === '/api/auth/refresh')).toHaveLength(1)
  })

  it.each([null, 'token-outra-conta'])('refresh tardio não restaura nem troca sessão (%s)', async (token) => {
    const refresh = deferred<Response>()
    fetchMock.mockResolvedValueOnce(resposta(401)).mockReturnValueOnce(refresh.promise)
    const pedido = api.GET('/api/me/progress')
    const rejected = expect(pedido).rejects.toMatchObject({ name: 'AbortError' })
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    setAccessToken(token)
    refresh.resolve(resposta(200, { access_token: 'atrasado' }))
    await rejected
    expect(sessionSnapshot().token).toBe(token)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('abortar durante refresh impede repetição sem cancelar a renovação compartilhada', async () => {
    const refresh = deferred<Response>()
    // Request é nativo do Node, portanto requer o AbortSignal do mesmo realm.
    const { transferableAbortController } = await import('node:util')
    const controller = transferableAbortController()
    fetchMock.mockResolvedValueOnce(resposta(401)).mockReturnValueOnce(refresh.promise)
    const pedido = api.GET('/api/me/progress', { signal: controller.signal })
    const rejected = expect(pedido).rejects.toMatchObject({ name: 'AbortError' })
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    controller.abort()
    refresh.resolve(resposta(200, { access_token: 'novo' }))
    await rejected
    expect(sessionSnapshot().token).toBe('novo')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('cookie de outra conta exige autenticação, nunca reenvia sob o novo usuário', async () => {
    setSessionUser(7)
    const perdeu = vi.fn()
    onSessaoPerdida(perdeu)
    fetchMock.mockResolvedValueOnce(resposta(401))
      .mockResolvedValueOnce(resposta(200, { access_token: 'conta-8' }))
      .mockResolvedValueOnce(resposta(200, { id: 8 }))
    expect((await api.GET('/api/me/progress')).response.status).toBe(401)
    expect(perdeu).toHaveBeenCalledTimes(1)
    expect(sessionSnapshot().token).toBeNull()
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('perfil não confirmado permite leitura pública sem token, mas bloqueia escritas', async () => {
    setSessionReadOnly(true)
    fetchMock.mockResolvedValueOnce(resposta(200, []))
    expect((await api.GET('/api/lessons')).response.status).toBe(200)
    expect((fetchMock.mock.calls[0]![0] as Request).headers.has('Authorization')).toBe(false)
    const result = await api.PUT('/api/writing/prompts/{prompt_id}/draft', {
      params: { path: { prompt_id: 1 } }, body: { text: 'Keep my text.', expected_revision: 0 },
    })
    expect(result.response.status).toBe(503)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('401 atrasado não reenvia enquanto outra chamada mantém a sessão pausada', async () => {
    const atrasada = deferred<Response>()
    fetchMock.mockReturnValueOnce(atrasada.promise)
    const pedido = api.GET('/api/me/progress')
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    setSessionReadOnly(true)
    atrasada.resolve(resposta(401))
    expect((await pedido).response.status).toBe(503)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})

describe('cutover de 13/11/2026: escritas revisionadas', () => {
  it('fora de produção, uma escrita sem expected_revision falha antes de sair do navegador', async () => {
    await expect(api.PUT('/api/writing/prompts/{prompt_id}/draft', {
      params: { path: { prompt_id: 4 } }, body: { text: 'Sem revisão.' },
    })).rejects.toThrow(/expected_revision.*PUT \/api\/writing\/prompts\/\{prompt_id\}\/draft/)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('null vale como ausente e a mensagem lista todos os campos que faltam', async () => {
    await expect(api.POST('/api/review/{item_id}/grade', {
      params: { path: { item_id: 9 } }, body: { quality: 4, expected_revision: null },
    })).rejects.toThrow(/expected_revision e idempotency_key/)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('o transporte sem tipos (authenticatedFetch) também é conferido', async () => {
    await expect(authenticatedFetch('/api/me/account', {
      method: 'DELETE', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: 'segredo', confirmation: 'EXCLUIR MINHA CONTA' }),
    })).rejects.toThrow(/operation_key/)
    expect(fetchMock).not.toHaveBeenCalled()
    fetchMock.mockResolvedValueOnce(resposta(202, { state: 'completed' }))
    const response = await authenticatedFetch('/api/me/account', {
      method: 'DELETE', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ operation_key: 'c0ffee00-0000-4000-8000-000000000001', password: 'segredo', confirmation: 'EXCLUIR MINHA CONTA' }),
    })
    expect(response.status).toBe(202)
  })

  it('rotas sem revisão no contrato e leituras não são tocadas pelo guard', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(resposta(200, {})))
    await api.PUT('/api/me/study-plan', {
      body: { weekly_minutes: 60, preferred_days: ['mon'], goal: 'travel', timezone: 'America/Sao_Paulo' },
    })
    await api.POST('/api/me/notebook', { body: { course_slug: 'voa-level-1', lesson_number: 31, kind: 'note', content: 'x' } })
    await api.GET('/api/writing/prompts/{prompt_id}/draft', { params: { path: { prompt_id: 4 } } })
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('428 liga o aviso de atualização, devolve a resposta ao chamador e não repete nem apaga nada', async () => {
    expect(revisionRequiredSnapshot()).toBe(false)
    fetchMock.mockResolvedValueOnce(resposta(428, { detail: { code: 'revision_required' } }))
    const { response } = await api.PUT('/api/writing/prompts/{prompt_id}/draft', {
      params: { path: { prompt_id: 4 } }, body: { text: 'Keep my text.', expected_revision: 2 },
    })
    expect(response.status).toBe(428)
    expect(revisionRequiredSnapshot()).toBe(true)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(sessionSnapshot().token).toBe('token-velho')
  })

  it('428 no upload binário também aciona o aviso', async () => {
    fetchMock.mockResolvedValueOnce(resposta(428))
    const response = await authenticatedFetch('/api/speaking/attempts/1/audio', {
      method: 'PUT', headers: { 'Content-Type': 'audio/webm' }, body: new Uint8Array([1]),
    })
    expect(response.status).toBe(428)
    expect(revisionRequiredSnapshot()).toBe(true)
  })
})
