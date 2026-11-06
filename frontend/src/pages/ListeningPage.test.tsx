import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import createClient from 'openapi-fetch'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { setAccessToken, setSessionReadOnly, setSessionUser } from '../api/client'
import type { RevisionedPaths } from '../api/revisionedWrites'
import type { ListeningInput, ListeningProgress, ListeningResource } from '../api/listening'
import { ListeningPage } from './ListeningPage'

vi.mock('../api/auth', () => ({ useSessao: () => ({ usuario: { id: 7 }, offline: false }) }))
vi.mock('../api/client', async (original) => {
  const module = await original<typeof import('../api/client')>()
  const client = createClient<RevisionedPaths>({ baseUrl: 'http://localhost', credentials: 'same-origin', fetch: req => globalThis.fetch(req) })
  client.use(module.autenticacao)
  return { ...module, api: client }
})

const hotel: ListeningResource = {
  slug: 'hotel', title: 'Na recepção do hotel', description: 'Pratique sua chegada.', topic: 'Viagens',
  level: 'A2', source: 'Test-English', source_url: 'https://test-english.com/listening/a2/hotel/',
  mode: 'external_link', availability: 'available', checked_on: '2026-11-05', version: 1, position: 1,
}
let catalog: ListeningResource[]
let progress: ListeningProgress[]
let configEnabled: boolean
let failure: string | null
let writeStatus: number
let writes: ListeningInput[]
let client: QueryClient
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

beforeEach(() => {
  catalog = [hotel, { ...hotel, slug: 'cidade', title: 'Passeio na cidade', topic: 'Cidade', position: 2, availability: 'unavailable' }]
  progress = []; configEnabled = true; failure = null; writeStatus = 200; writes = []
  setSessionUser(7); setSessionReadOnly(false); setAccessToken('synthetic-token')
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true)
  client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const request = input as Request
    const path = new URL(request.url).pathname
    expect(request.headers.get('Authorization')).toBe('Bearer synthetic-token')
    if (path === failure) return json({}, 503)
    if (path.endsWith('/native-config')) return json({ enabled: false, preview: false })
    if (path.endsWith('/config')) return json({ enabled: configEnabled })
    if (path.endsWith('/resources')) return json(catalog)
    if (request.method === 'PUT') {
      const body = await request.json() as ListeningInput
      writes.push(body)
      expect(body.operation_key).toMatch(/^[0-9a-f-]{36}$/)
      if (writeStatus !== 200) return json({}, writeStatus)
      const saved = { resource_slug: 'hotel', state: body.state, revision: body.expected_revision + 1, updated_at: '2026-11-05T12:00:00Z' }
      progress = [saved]
      return json(saved)
    }
    return json(progress)
  }))
})

afterEach(() => {
  cleanup(); client.clear(); vi.restoreAllMocks(); vi.unstubAllGlobals()
  setAccessToken(null); setSessionUser(null); setSessionReadOnly(false)
})

function show() { render(<QueryClientProvider client={client}><ListeningPage /></QueryClientProvider>) }
const selection = () => screen.getByLabelText('Meu progresso em Na recepção do hotel')

it('mostra origem, nova aba e indisponibilidade sem marcar ao abrir o link', async () => {
  show()
  const link = await screen.findByRole('link', { name: /Abrir no Test-English/ })
  expect(link).toHaveAttribute('href', hotel.source_url)
  expect(link).toHaveAttribute('target', '_blank')
  expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  expect(screen.getByText(/Link indisponível/)).toBeVisible()
  expect(screen.getByText(/A conclusão é informada por você/)).toBeVisible()
  expect(selection()).toHaveValue('not_started')
  expect(document.querySelector('iframe, video, audio, img')).toBeNull()
  expect(writes).toHaveLength(0)
})

it('busca sem acentos e filtra progresso com resultado vazio explícito', async () => {
  progress = [{ resource_slug: 'hotel', state: 'completed', revision: 2, updated_at: '2026-11-05T12:00:00Z' }]
  show(); await screen.findByLabelText('Buscar assunto')
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Buscar assunto'), 'recepcao')
  expect(screen.getByText('1 de 2 atividades')).toBeVisible()
  await user.selectOptions(screen.getByLabelText('Filtrar por progresso'), 'in_progress')
  expect(screen.getByText(/Nenhuma atividade corresponde/)).toBeVisible()
  await user.clear(screen.getByLabelText('Buscar assunto'))
  await user.selectOptions(screen.getByLabelText('Filtrar por progresso'), 'completed')
  expect(selection()).toHaveValue('completed')
})

it('confirma somente após a API e permite desfazer a conclusão', async () => {
  show(); await screen.findByLabelText('Buscar assunto')
  const user = userEvent.setup()
  await user.selectOptions(selection(), 'completed')
  await screen.findByText('Marcação confirmada.')
  await waitFor(() => expect(selection()).toHaveValue('completed'))
  expect(writes[0]).toMatchObject({ expected_revision: 0, state: 'completed' })
  await user.selectOptions(selection(), 'not_started')
  await waitFor(() => expect(writes).toHaveLength(2))
  await waitFor(() => expect(selection()).toHaveValue('not_started'))
  expect(writes[1]).toMatchObject({ expected_revision: 1 })
})

it('falha de rede preserva estado confirmado e repete a mesma chave ao tentar novamente', async () => {
  writeStatus = 503
  show(); await screen.findByLabelText('Buscar assunto')
  const user = userEvent.setup()
  await user.selectOptions(selection(), 'in_progress')
  await screen.findByText(/Não foi possível confirmar a marcação/)
  expect(selection()).toHaveValue('not_started')
  expect(screen.queryByText('Marcação confirmada.')).toBeNull()
  writeStatus = 200
  await waitFor(() => expect(screen.getByRole('button', { name: 'Tentar salvar novamente' })).toBeEnabled())
  await user.click(screen.getByRole('button', { name: 'Tentar salvar novamente' }))
  await screen.findByText('Marcação confirmada.')
  expect(writes).toHaveLength(2)
  expect(writes[1]).toEqual(writes[0])
})

it('conflito atualiza o estado de outra aba e exige nova decisão', async () => {
  show(); await screen.findByLabelText('Buscar assunto')
  writeStatus = 409
  progress = [{ resource_slug: 'hotel', state: 'completed', revision: 4, updated_at: '2026-11-05T12:00:00Z' }]
  await userEvent.setup().selectOptions(selection(), 'in_progress')
  await screen.findByText(/O progresso mudou em outra aba/)
  await waitFor(() => expect(selection()).toHaveValue('completed'))
  expect(screen.queryByRole('button', { name: 'Tentar salvar novamente' })).toBeNull()
})

it('offline bloqueia escrita e não cria fila automática', async () => {
  show(); await screen.findByLabelText('Buscar assunto')
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
  void act(() => { window.dispatchEvent(new Event('offline')) })
  expect(selection()).toBeDisabled()
  expect(screen.getByText(/Conecte-se à internet/)).toBeVisible()
  expect(writes).toHaveLength(0)
})

it.each(['/api/listening/config', '/api/listening/resources', '/api/me/listening/progress'])('falha em %s oferece recuperação sem inventar progresso vazio', async path => {
  failure = path
  show(); await screen.findByRole('alert')
  expect(screen.queryByLabelText('Meu progresso em Na recepção do hotel')).toBeNull()
  failure = null
  await userEvent.setup().click(screen.getByRole('button', { name: 'Tentar novamente' }))
  await screen.findByLabelText('Buscar assunto')
})

it('flag desligada não busca catálogo nem progresso', async () => {
  configEnabled = false
  show(); await screen.findByText(/Listening rápido ainda não está disponível/)
  expect(fetch).toHaveBeenCalledTimes(2)
  expect(screen.queryByLabelText('Buscar assunto')).toBeNull()
})
