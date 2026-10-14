import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { StrictMode, useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessaoProvider, useSessao } from './auth'
import { api, setAccessToken, setSessionReadOnly, setSessionUser } from './client'
import { sessionSnapshot } from './session'
import { SessionStatus } from '../components/SessionStatus'
import { listQueuedAttempts, queueAttempt, syncAttemptQueue } from '../features/offline/attemptQueue'
import { WritingWorkspace } from '../features/writing/WritingWorkspace'

// Transporte real, com URL absoluta para o Request do Node. Não mockamos a
// lógica de sessão: atravessamos bootstrap, middleware e provider.
vi.mock('./client', async (importOriginal) => {
  const original = await importOriginal<typeof import('./client')>()
  const { default: createClient } = await import('openapi-fetch')
  const client = createClient({ baseUrl: 'http://localhost', credentials: 'same-origin', fetch: (req) => fetch(req) })
  client.use(original.autenticacao)
  return { ...original, api: client }
})

const perfil = { id: 7, email: 'aluno@example.com', display_name: 'Aluno' }
const perfilKey = 'aulas:last-user:v1'

function response(status: number, body: unknown = {}) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}
function path(input: Request | string) {
  return new URL(typeof input === 'string' ? input : input.url, 'http://localhost').pathname
}
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

function EstadoDaSessao({ workspace = false }: { workspace?: boolean }) {
  const { usuario, carregando, estado, sair, entrar, registrar } = useSessao()
  const [texto, setTexto] = useState('Rascunho ainda em edição.')
  if (carregando) return <p>carregando</p>
  return <>
    <p>{usuario ? `${usuario.display_name} · ${estado}` : `sem sessão · ${estado}`}</p>
    <SessionStatus />
    {usuario && <textarea aria-label="Rascunho" value={texto} onChange={(e) => setTexto(e.target.value)} />}
    {usuario && workspace && <WritingWorkspace userId={usuario.id} prompt={{
      id: 4, position: 0, title: 'Writing', instructions: 'Write a sentence.',
      min_words: 3, min_sentences: 1, requirements: [],
    }} />}
    {!usuario && <>
      <button onClick={() => void entrar('aluno@example.com', 'senha-de-teste')}>Entrar</button>
      <button onClick={() => void registrar('aluno@example.com', 'senha-de-teste', 'Aluno')}>Criar conta</button>
    </>}
    <button onClick={() => void sair()}>Sair</button>
  </>
}

function montar(strict = false, workspace = false) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const app = <QueryClientProvider client={queryClient}>
    <SessaoProvider><EstadoDaSessao workspace={workspace} /></SessaoProvider>
  </QueryClientProvider>
  return { ...render(strict ? <StrictMode>{app}</StrictMode> : app), queryClient }
}

let fetchMock: ReturnType<typeof vi.fn>
beforeEach(() => {
  setAccessToken(null)
  setSessionReadOnly(false)
  setSessionUser(null)
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  localStorage.clear()
  setAccessToken(null)
  vi.unstubAllGlobals()
})

function servidorValido() {
  fetchMock.mockImplementation(async (input: Request | string) => {
    if (path(input) === '/api/auth/refresh') return response(200, { access_token: 'access' })
    if (path(input) === '/api/auth/me') return response(200, perfil)
    return response(200)
  })
}

describe('SessaoProvider e transporte integrados', () => {
  it('faz uma única renovação inicial mesmo sob StrictMode', async () => {
    servidorValido()
    montar(true)
    expect(await screen.findByText('Aluno · valida')).toBeInTheDocument()
    expect(fetchMock.mock.calls.filter((call) => path(call[0]) === '/api/auth/refresh')).toHaveLength(1)
    expect(sessionSnapshot().token).toBe('access')
    expect(JSON.parse(localStorage.getItem(perfilKey)!)).toEqual({ id: 7, display_name: 'Aluno' })
    expect(localStorage.getItem(perfilKey)).not.toContain('access')
  })

  it('restaura somente o perfil mínimo offline, sem autorizar escritas', async () => {
    localStorage.setItem(perfilKey, JSON.stringify({ id: 7, display_name: 'Aluno' }))
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
    fetchMock.mockRejectedValue(new TypeError('Offline'))
    montar()
    expect(await screen.findByText('Aluno · offline')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('sem conexão')
    expect(sessionSnapshot()).toMatchObject({ token: null, perfilNaoConfirmado: true })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('503 no bootstrap mantém perfil e dados locais, com recuperação explícita', async () => {
    localStorage.setItem(perfilKey, JSON.stringify({ id: 7, display_name: 'Aluno' }))
    localStorage.setItem('rascunho-fixture', 'Texto local')
    fetchMock.mockResolvedValue(response(503))
    montar()
    expect(await screen.findByText('Aluno · indisponivel')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('temporariamente indisponível')
    expect(screen.getByRole('status')).not.toHaveTextContent('sem conexão')
    servidorValido()
    fireEvent.click(screen.getByRole('button', { name: 'Tentar confirmar sessão' }))
    expect(await screen.findByText('Aluno · valida')).toBeInTheDocument()
    expect(localStorage.getItem('rascunho-fixture')).toBe('Texto local')
    expect(sessionSnapshot().perfilNaoConfirmado).toBe(false)
  })

  it('indisponibilidade sem perfil oferece retry sem afirmar sessão revogada', async () => {
    fetchMock.mockResolvedValue(response(503))
    montar()
    expect(await screen.findByText('sem sessão · indisponivel')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Tentar confirmar sessão' })).toBeEnabled()
  })

  it('falha transitória durante estudo conserva editor, cache e fila pendente', async () => {
    servidorValido()
    const { queryClient } = montar()
    await screen.findByText('Aluno · valida')
    fireEvent.change(screen.getByLabelText('Rascunho'), { target: { value: 'Meu texto não pode sumir.' } })
    queryClient.setQueryData(['draft', 7], 'rascunho em cache')
    await queueAttempt({ userId: 7, exerciseId: 31, answer: 'better', idempotencyKey: 'a-7', createdAt: '2026-10-13T10:00:00Z' })
    fetchMock.mockImplementation(async (input: Request | string) => (
      path(input) === '/api/auth/refresh' ? response(503) : response(401)
    ))
    await act(async () => {
      const result = await syncAttemptQueue(7)
      expect(result).toMatchObject({ synced: 0, pending: 1, blocked: 0 })
    })
    expect(await screen.findByText('Aluno · indisponivel')).toBeInTheDocument()
    expect(screen.getByLabelText('Rascunho')).toHaveValue('Meu texto não pode sumir.')
    expect(queryClient.getQueryData(['draft', 7])).toBe('rascunho em cache')
    expect((await listQueuedAttempts(7))[0]?.idempotencyKey).toBe('a-7')
    expect(localStorage.getItem(perfilKey)).not.toBeNull()
  })

  it('autosave real de WritingWorkspace mantém texto e backup após refresh 503', async () => {
    fetchMock.mockImplementation(async (input: Request | string) => {
      const route = path(input)
      if (route === '/api/auth/refresh') return response(200, { access_token: 'access' })
      if (route === '/api/auth/me') return response(200, perfil)
      if (route === '/api/writing/prompts/4/draft') return response(200, { text: '', revisions: [] })
      return response(200, { writing_enabled: false })
    })
    montar(false, true)
    const editor = await screen.findByRole('textbox', { name: 'Seu texto em inglês' })
    await waitFor(() => expect(editor).toBeEnabled())
    fetchMock.mockImplementation(async (input: Request | string) => {
      if (path(input) === '/api/auth/refresh') return response(503)
      await (input as Request).text()
      return response(401)
    })
    fireEvent.change(editor, { target: { value: 'This text stays in my notebook.' } })
    await screen.findByText('Salvo neste dispositivo; sincronização pendente.', {}, { timeout: 3000 })
    expect(await screen.findByText('Aluno · indisponivel')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Seu texto em inglês' })).toBe(editor)
    expect(editor).toHaveValue('This text stays in my notebook.')
    expect(localStorage.getItem('aulas-ingles:writing-draft:v1:7:4')).toBe('This text stays in my notebook.')
  })

  it.each(['Entrar', 'Criar conta'])('%s confirma perfil e libera envio após autenticação explícita', async (button) => {
    fetchMock.mockResolvedValueOnce(response(401))
    montar()
    await screen.findByText('sem sessão · expirada')
    fetchMock.mockResolvedValueOnce(response(200, { access_token: 'login-novo' }))
      .mockResolvedValueOnce(response(200, perfil))
    fireEvent.click(screen.getByRole('button', { name: button }))
    expect(await screen.findByText('Aluno · valida')).toBeInTheDocument()
    expect(sessionSnapshot()).toMatchObject({ token: 'login-novo', perfilNaoConfirmado: false })
  })

  it('refresh revogado remove apenas perfil/cache de sessão, não rascunhos/fila', async () => {
    servidorValido()
    const { queryClient } = montar()
    await screen.findByText('Aluno · valida')
    queryClient.setQueryData(['private', 7], 'conteúdo privado')
    localStorage.setItem('rascunho-fixture', 'guardar')
    await queueAttempt({ userId: 7, exerciseId: 31, answer: 'better', idempotencyKey: 'a-7', createdAt: '2026-10-13T10:00:00Z' })
    fetchMock.mockResolvedValue(response(401))
    await act(async () => { await api.GET('/api/me/progress') })
    expect(screen.getByText('sem sessão · expirada')).toBeInTheDocument()
    expect(queryClient.getQueryData(['private', 7])).toBeUndefined()
    expect(localStorage.getItem(perfilKey)).toBeNull()
    expect(localStorage.getItem('rascunho-fixture')).toBe('guardar')
    expect(await listQueuedAttempts(7)).toHaveLength(1)
    expect(sessionSnapshot().token).toBeNull()
  })

  it('401 no bootstrap é revogação mesmo se navigator.onLine estiver falso', async () => {
    localStorage.setItem(perfilKey, JSON.stringify({ id: 7, display_name: 'Aluno' }))
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
    fetchMock.mockResolvedValue(response(401))
    montar()
    expect(await screen.findByText('sem sessão · expirada')).toBeInTheDocument()
    expect(localStorage.getItem(perfilKey)).toBeNull()
  })

  it('erro ao carregar perfil após refresh mantém sessão local bloqueada para escrita', async () => {
    localStorage.setItem(perfilKey, JSON.stringify({ id: 7, display_name: 'Aluno' }))
    fetchMock.mockResolvedValueOnce(response(200, { access_token: 'novo' }))
      .mockResolvedValueOnce(response(200, { id: 7 }))
      .mockResolvedValueOnce(response(503))
    montar()
    expect(await screen.findByText('Aluno · indisponivel')).toBeInTheDocument()
    expect(sessionSnapshot().perfilNaoConfirmado).toBe(true)
    const result = await api.PUT('/api/writing/prompts/{prompt_id}/draft', {
      params: { path: { prompt_id: 31 } }, body: { text: 'Keep this draft.' },
    })
    expect(result.response.status).toBe(503)
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('reconexão com falha em /me não causa rejeição não tratada', async () => {
    localStorage.setItem(perfilKey, JSON.stringify({ id: 7, display_name: 'Aluno' }))
    fetchMock.mockRejectedValue(new TypeError('Offline'))
    montar()
    await screen.findByText('Aluno · indisponivel')
    fetchMock.mockResolvedValueOnce(response(200, { access_token: 'novo' }))
      .mockResolvedValueOnce(response(503))
    fireEvent(window, new Event('online'))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Tentar confirmar sessão' })).toBeEnabled())
    expect(screen.getByText('Aluno · indisponivel')).toBeInTheDocument()
    expect(sessionSnapshot().perfilNaoConfirmado).toBe(true)
  })

  it('quota do perfil não desfaz autenticação nem finge persistência local', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('Quota', 'QuotaExceededError') })
    servidorValido()
    montar()
    expect(await screen.findByText('Aluno · valida')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('perfil local não pôde ser atualizado')
    expect(sessionSnapshot().token).toBe('access')
  })

  it('logout permanece efetivo quando storage e servidor falham', async () => {
    servidorValido()
    montar()
    await screen.findByText('Aluno · valida')
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => { throw new Error('Storage blocked') })
    fetchMock.mockRejectedValueOnce(new TypeError('Offline'))
    fireEvent.click(screen.getByRole('button', { name: 'Sair' }))
    expect(await screen.findByText('sem sessão · expirada')).toBeInTheDocument()
    expect(await screen.findByText(/não foi possível confirmar o encerramento no servidor/)).toBeInTheDocument()
    expect(sessionSnapshot().token).toBeNull()
  })

  it('logout HTTP 503 avisa que não confirmou a revogação remota', async () => {
    servidorValido()
    montar()
    await screen.findByText('Aluno · valida')
    fetchMock.mockResolvedValueOnce(response(503))
    fireEvent.click(screen.getByRole('button', { name: 'Sair' }))
    expect(await screen.findByText(/não foi possível confirmar o encerramento no servidor/)).toBeInTheDocument()
    expect(screen.getByText('sem sessão · expirada')).toBeInTheDocument()
  })

  it('perfil tardio não restaura usuário após logout', async () => {
    const atrasado = deferred<Response>()
    servidorValido()
    montar()
    await screen.findByText('Aluno · valida')
    fetchMock.mockResolvedValueOnce(response(401)).mockResolvedValueOnce(response(503))
    await act(async () => { await api.GET('/api/me/progress') })
    fetchMock.mockResolvedValueOnce(response(200, { access_token: 'novo' }))
      .mockResolvedValueOnce(response(200, { id: 7 }))
      .mockReturnValueOnce(atrasado.promise)
    fireEvent.click(screen.getByRole('button', { name: 'Tentar confirmar sessão' }))
    await waitFor(() => expect(sessionSnapshot().token).toBe('novo'))
    fetchMock.mockResolvedValueOnce(response(200))
    fireEvent.click(screen.getByRole('button', { name: 'Sair' }))
    await screen.findByText('sem sessão · expirada')
    await act(async () => { atrasado.resolve(response(200, perfil)) })
    expect(screen.getByText('sem sessão · expirada')).toBeInTheDocument()
    expect(sessionSnapshot().token).toBeNull()
    expect(localStorage.getItem(perfilKey)).toBeNull()
  })

  it('troca da conta no cookie não associa o perfil local ao novo token', async () => {
    localStorage.setItem(perfilKey, JSON.stringify({ id: 7, display_name: 'Aluno' }))
    fetchMock.mockResolvedValueOnce(response(200, { access_token: 'conta-8' }))
      .mockResolvedValueOnce(response(200, { id: 8, display_name: 'Outro' }))
    montar()
    expect(await screen.findByText('sem sessão · expirada')).toBeInTheDocument()
    expect(sessionSnapshot().token).toBeNull()
    expect(localStorage.getItem(perfilKey)).toBeNull()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
