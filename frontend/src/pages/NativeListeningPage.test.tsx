import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import createClient from 'openapi-fetch'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { setAccessToken, setSessionReadOnly, setSessionUser } from '../api/client'
import type { RevisionedPaths } from '../api/revisionedWrites'
import type { NativeActivity, NativeResponse, NativeSession } from '../api/nativeListening'
import { NativeListeningPage } from './NativeListeningPage'

vi.mock('../api/auth', () => ({ useSessao: () => ({ usuario: { id: 7 }, offline: false }) }))
vi.mock('../api/client', async original => {
  const module = await original<typeof import('../api/client')>()
  const client = createClient<RevisionedPaths>({ baseUrl: 'http://localhost', fetch: req => globalThis.fetch(req) })
  client.use(module.autenticacao)
  return { ...module, api: client }
})

const activity: NativeActivity = {
  slug: 'weekend', title: 'Weekend plans', topic: 'Lazer', level: 'A2', preview: true, version: 1,
  instructions: 'Listen and choose.', audio_duration_seconds: 77, attribution: 'Original preview', rights_note: 'Review pending',
  map_rows: [['A Library', 'B Museum'], ['C Station', 'D Park']], map_description: 'North is at the top.',
  questions: [
    { id: 'activities', prompt: 'Which TWO activities?', kind: 'multi_select', selection_count: 2,
      options: [{ id: 'bike', label: 'Ride bikes' }, { id: 'lunch', label: 'Have lunch' }, { id: 'film', label: 'Watch a film' }] },
    { id: 'meeting', prompt: 'Where do they meet?', kind: 'single_choice', selection_count: 1,
      options: [{ id: 'park', label: 'Park gate' }, { id: 'home', label: 'At home' }] },
    { id: 'time', prompt: 'When do they meet?', kind: 'single_choice', selection_count: 1,
      options: [{ id: 'ten', label: 'Ten' }, { id: 'nine', label: 'Nine' }] },
  ],
}
let current: NativeSession
let client: QueryClient
let writes: NativeResponse[]
let responseStatus: number
let audioStatus: number
let startStatus: number
let detailStatus: number
const revokeUrl = vi.fn()
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

beforeEach(() => {
  current = { id: 11, activity, revision: 0, completed: false, score: 0, total: 3,
    support_revealed: false, transcript: null, feedback: [], created_at: '2026-11-05T12:00:00Z' }
  localStorage.clear()
  writes = []; responseStatus = 200; audioStatus = 200; startStatus = 200; detailStatus = 200
  setSessionUser(7); setSessionReadOnly(false); setAccessToken('synthetic-token')
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true)
  URL.createObjectURL = vi.fn(() => 'blob:preview')
  revokeUrl.mockClear()
  URL.revokeObjectURL = revokeUrl
  client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const request = input as Request
    const path = new URL(request.url).pathname
    expect(request.headers.get('Authorization')).toBe('Bearer synthetic-token')
    if (path.endsWith('/position')) return json({ session_id: 11, position_seconds: 0, revision: 0, completed: false, operation_key: null, changed_at: null, updated_at: null })
    if (path.endsWith('/audio')) return new Response('synthetic-audio', { status: audioStatus, headers: { 'Content-Type': 'audio/mpeg' } })
    if (path.endsWith('/responses')) {
      const body = await request.json() as NativeResponse
      writes.push(body)
      if (responseStatus !== 200) return json({}, responseStatus)
      current.revision++
      if (body.kind === 'transcript') {
        current.support_revealed = true; current.transcript = 'Maya: Let us ride bikes.'
      } else {
        const first = !current.feedback.some(row => row.question_id === body.question_id)
        const answers = body.question_id === 'activities' ? ['bike', 'lunch'] : body.question_id === 'meeting' ? ['park'] : ['ten']
        const correct = body.kind === 'answer' && [...(body.selected_ids ?? [])].sort().join() === answers.sort().join()
        current.score += first && correct ? 1 : 0
        current.feedback.push({ question_id: body.question_id!, kind: body.kind, selected_ids: body.selected_ids ?? [],
          correct, first_response: first, answer_ids: answers, explanation: 'They agree on these plans.' })
        current.completed = new Set(current.feedback.map(row => row.question_id)).size === 3
      }
      return json(current)
    }
    if (path.endsWith('/sessions')) return json(current, startStatus)
    if (path.includes('/sessions/')) return json(current)
    return json(activity, detailStatus)
  }))
})

afterEach(() => {
  cleanup(); client.clear(); vi.restoreAllMocks(); vi.unstubAllGlobals()
  setAccessToken(null); setSessionUser(null); setSessionReadOnly(false)
})

function show(saved = false) {
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[`/listening/weekend${saved ? '?sessao=11' : ''}`]}>
    <Routes><Route path="/listening/:slug" element={<NativeListeningPage />} /></Routes>
  </MemoryRouter></QueryClientProvider>)
}
async function begin() {
  show()
  await userEvent.click(await screen.findByRole('button', { name: 'Iniciar prática' }))
  await screen.findAllByRole('group', { name: 'Sua resposta' })
  await waitFor(() => expect(document.querySelector('audio')).not.toBeNull())
}
const first = () => within(screen.getByRole('region', { name: '1. Which TWO activities?' }))

it('inicia sob ação, não inclui gabarito/transcrição e oferece mapa acessível', async () => {
  show()
  await screen.findByText('Weekend plans')
  expect(document.querySelector('audio')).toBeNull()
  expect(writes).toHaveLength(0)
  await userEvent.click(screen.getByRole('button', { name: 'Iniciar prática' }))
  expect(await screen.findByText('North is at the top.')).toBeVisible()
  expect(screen.queryByText('They agree on these plans.')).toBeNull()
  await waitFor(() => expect(document.querySelector('audio')).not.toBeNull())
  expect(document.querySelector('audio')).not.toHaveAttribute('autoplay')
  expect(document.querySelector('audio')).toHaveAttribute('preload', 'metadata')
  expect(screen.getByText(/Prévia local para revisão/)).toBeVisible()
})

it('exige exatamente duas opções e envia IDs, sem corrigir no cliente', async () => {
  await begin()
  const q = first()
  expect(q.getByRole('button', { name: 'Confirmar resposta' })).toBeDisabled()
  await userEvent.click(q.getByLabelText('Ride bikes'))
  expect(q.getByRole('button', { name: 'Confirmar resposta' })).toBeDisabled()
  await userEvent.click(q.getByLabelText('Have lunch'))
  await userEvent.click(q.getByLabelText('Watch a film'))
  expect(q.getByRole('button', { name: 'Confirmar resposta' })).toBeDisabled()
  await userEvent.click(q.getByLabelText('Watch a film'))
  await userEvent.click(q.getByRole('button', { name: 'Confirmar resposta' }))
  expect(await q.findByText(/Resposta correta/)).toBeVisible()
  expect(writes[0]).toMatchObject({ selected_ids: ['bike', 'lunch'], expected_revision: 0, question_id: 'activities' })
  await waitFor(() => expect(q.getByRole('button', { name: 'Responder novamente' })).toBeEnabled())
  await userEvent.click(q.getByRole('button', { name: 'Responder novamente' }))
  expect(await q.findByText(/Repetição: a nota inicial foi mantida/)).toBeVisible()
  expect(current.score).toBe(1)
})

it('revela resposta com nota zero e identifica apoio textual', async () => {
  await begin()
  await userEvent.click(first().getByRole('button', { name: 'Revelar resposta' }))
  expect(await first().findByText(/Resposta revelada/)).toBeVisible()
  expect(current.score).toBe(0)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Revelar transcrição como apoio' })).toBeEnabled())
  await userEvent.click(screen.getByRole('button', { name: 'Revelar transcrição como apoio' }))
  expect(await screen.findByText('Maya: Let us ride bikes.')).toBeVisible()
  expect(screen.getByText(/prática com apoio textual/)).toBeVisible()
})

it('preserva chave da resposta não confirmada ao tentar novamente', async () => {
  await begin(); responseStatus = 503
  await userEvent.click(first().getByRole('button', { name: 'Revelar resposta' }))
  await screen.findByRole('button', { name: 'Tentar enviar novamente' })
  expect(first().getByRole('button', { name: 'Revelar resposta' })).toBeDisabled()
  responseStatus = 200
  await userEvent.click(screen.getByRole('button', { name: 'Tentar enviar novamente' }))
  await first().findByText(/Resposta revelada/)
  expect(writes[0]).toEqual(writes[1])
})

it('recarrega a sessão após conflito sem repetir automaticamente a resposta', async () => {
  await begin(); responseStatus = 409; current.revision = 2
  await userEvent.click(first().getByRole('button', { name: 'Revelar resposta' }))
  expect(await screen.findByText(/a sessão mudou em outra aba/)).toBeVisible()
  expect(writes).toHaveLength(1)
  expect(first().getByRole('button', { name: 'Revelar resposta' })).toBeDisabled()
  responseStatus = 200
  await waitFor(() => expect(screen.getByRole('button', { name: 'Enviar como nova tentativa' })).toBeEnabled())
  await userEvent.click(screen.getByRole('button', { name: 'Enviar como nova tentativa' }))
  await first().findByText(/Resposta revelada/)
  expect(writes[1]?.expected_revision).toBe(2)
  expect(writes[1]?.operation_key).not.toBe(writes[0]?.operation_key)
})

it('salva resposta offline e envia após reconectar', async () => {
  await begin()
  await userEvent.click(first().getByLabelText('Ride bikes'))
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
  act(() => { window.dispatchEvent(new Event('offline')) })
  expect(first().getByLabelText('Ride bikes')).toBeChecked()
  expect(first().getByLabelText('Ride bikes')).toBeEnabled()
  await userEvent.click(first().getByLabelText('Have lunch'))
  await userEvent.click(first().getByRole('button', { name: 'Confirmar resposta' }))
  await screen.findByText(/1 resposta\(s\) pendente/)
  expect(writes).toHaveLength(0)
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true)
  act(() => { window.dispatchEvent(new Event('online')) })
  await first().findByText(/Resposta correta/)
  expect(writes).toHaveLength(1)
})

it('áudio indisponível tem recuperação e libera o blob ao sair', async () => {
  audioStatus = 503; show(true)
  await screen.findByRole('button', { name: 'Tentar carregar áudio' })
  audioStatus = 200
  await userEvent.click(screen.getByRole('button', { name: 'Tentar carregar áudio' }))
  await waitFor(() => expect(document.querySelector('audio')).not.toBeNull())
  cleanup()
  expect(revokeUrl).toHaveBeenCalledWith('blob:preview')
})

it('controla velocidade, avanço e repetição A/B com o player compartilhado', async () => {
  await begin()
  const audio = document.querySelector('audio')!
  await userEvent.selectOptions(screen.getByLabelText('Velocidade do áudio'), '0.75')
  expect(audio.playbackRate).toBe(0.75)
  audio.currentTime = 10; fireEvent.timeUpdate(audio)
  await userEvent.click(screen.getByRole('button', { name: 'Marcar início A' }))
  audio.currentTime = 20; fireEvent.timeUpdate(audio)
  await userEvent.click(screen.getByRole('button', { name: 'Marcar fim B' }))
  audio.currentTime = 21; fireEvent.timeUpdate(audio)
  expect(audio.currentTime).toBe(10)
  await userEvent.click(screen.getByRole('button', { name: 'Limpar trecho' }))
  await userEvent.click(screen.getByRole('button', { name: '+5 s' }))
  expect(audio.currentTime).toBe(15)
})

it('retoma sessão salva com versão fixa e mostra conclusão confirmada', async () => {
  current.completed = true; current.score = 2
  current.activity = { ...activity, version: 1, title: 'Saved version' }
  show(true)
  expect(await screen.findByRole('heading', { level: 1, name: 'Saved version' })).toBeVisible()
  expect(screen.getByText(/Prática concluída/)).toHaveTextContent('2 de 3')
  expect(screen.queryByRole('button', { name: 'Iniciar prática' })).toBeNull()
})

it('oferece nova tentativa para início e carregamento indisponíveis', async () => {
  detailStatus = 503; show()
  await screen.findByRole('button', { name: 'Tentar novamente' })
  detailStatus = 200; startStatus = 503
  await userEvent.click(screen.getByRole('button', { name: 'Tentar novamente' }))
  await userEvent.click(await screen.findByRole('button', { name: 'Iniciar prática' }))
  await screen.findByRole('button', { name: 'Tentar iniciar novamente' })
  startStatus = 200
  await userEvent.click(screen.getByRole('button', { name: 'Tentar iniciar novamente' }))
  await screen.findByText(/Primeiras respostas/)
})
