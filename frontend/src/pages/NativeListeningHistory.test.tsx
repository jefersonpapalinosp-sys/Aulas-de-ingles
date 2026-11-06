import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import createClient from 'openapi-fetch'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { RevisionedPaths } from '../api/revisionedWrites'
import { setAccessToken, setSessionReadOnly, setSessionUser } from '../api/client'
import { NativeListeningHistory } from './NativeListeningHistory'

vi.mock('../api/auth', () => ({ useSessao: () => ({ usuario: { id: 7 }, offline: false }) }))
vi.mock('../api/client', async original => {
  const module = await original<typeof import('../api/client')>()
  const client = createClient<RevisionedPaths>({ baseUrl: 'http://localhost', fetch: req => globalThis.fetch(req) })
  client.use(module.autenticacao)
  return { ...module, api: client }
})
let client: QueryClient
let paths: URL[]
let failure: boolean
beforeEach(() => {
  setSessionUser(7); setAccessToken('synthetic'); setSessionReadOnly(false)
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true)
  paths = []; failure = false
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  vi.stubGlobal('fetch', vi.fn((request: Request) => {
    const url = new URL(request.url); paths.push(url)
    const older = url.searchParams.has('before')
    return Promise.resolve(new Response(JSON.stringify({ items: [{ session_id: older ? 1 : 2,
      slug: 'hotel-riverside', version: 1, title: older ? 'Older hotel' : 'Recent hotel',
      available: !older, completed: false, first_score: 0, latest_score: 1, total: 4, answered: 1,
      support_revealed: true, started_at: '2026-11-05T12:00:00Z', last_response_at: null, position_seconds: 5 }],
      attempts: 2, next_before: older ? null : 2,
      first_attempt_at: '2026-11-04T12:00:00Z', last_attempt_at: '2026-11-05T12:00:00Z',
    }), { status: failure ? 503 : 200, headers: { 'Content-Type': 'application/json' } }))
  }))
})
afterEach(() => { cleanup(); client.clear(); vi.restoreAllMocks(); vi.unstubAllGlobals(); setAccessToken(null); setSessionUser(null) })
function show() {
  render(<QueryClientProvider client={client}><MemoryRouter><NativeListeningHistory userId={7} /></MemoryRouter></QueryClientProvider>)
}

it('paginação usa cursor, preserva notas e identifica conteúdo indisponível', async () => {
  show()
  expect(await screen.findByRole('link', { name: /Continuar de onde parei/ })).toHaveAttribute('href', '/listening/hotel-riverside?sessao=2')
  expect(screen.getByText('Primeiras respostas: 0/4. Últimas tentativas: 1/4.')).toBeVisible()
  expect(screen.getByRole('link', { name: 'Revisar erros' })).toHaveAttribute('href', '/listening/hotel-riverside?sessao=2&erros=1')
  await userEvent.click(screen.getByRole('button', { name: 'Mais antigas' }))
  await screen.findByText('Conteúdo indisponível; histórico preservado.')
  expect(paths.some(url => url.searchParams.get('before') === '2')).toBe(true)
  expect(screen.getByRole('button', { name: 'Mais antigas' })).toBeDisabled()
  await userEvent.click(screen.getByRole('button', { name: 'Mais recentes' }))
  await screen.findByRole('heading', { name: 'Recent hotel' })
})

it('filtro reinicia o cursor e falha permite nova consulta', async () => {
  failure = true; show()
  await screen.findByRole('alert')
  failure = false
  await userEvent.click(screen.getByRole('button', { name: 'Atualizar histórico' }))
  await screen.findByRole('heading', { name: 'Recent hotel' })
  await userEvent.click(screen.getByRole('button', { name: 'Mais antigas' }))
  await screen.findByRole('heading', { name: 'Older hotel' })
  await userEvent.selectOptions(screen.getByLabelText('Filtrar histórico por atividade'), 'sabado-com-amigos')
  await waitFor(() => expect(paths.at(-1)?.searchParams.get('slug')).toBe('sabado-com-amigos'))
  expect(paths.at(-1)?.searchParams.has('before')).toBe(false)
})

it('offline não busca histórico privado na rede', async () => {
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
  show()
  await screen.findByRole('heading', { name: 'Meu histórico no aplicativo' })
  expect(paths).toHaveLength(0)
})
