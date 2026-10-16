import { act, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ActiveStudyTime } from './ActiveStudyTime'

const { post, gate } = vi.hoisted(() => ({ post: vi.fn(), gate: { online: true, user: 7 } }))
vi.mock('../../api/client', () => ({ api: { POST: post } }))
vi.mock('../../api/media', () => ({ canSyncFor: (user: number) => gate.online && user === gate.user }))
const events = () => post.mock.calls.filter(([url]) => url.endsWith('/events'))
const savedEvents = () => Object.keys(localStorage).filter((key) => key.startsWith('aulas-ingles:activity-event:'))
const mount = () => render(<QueryClientProvider client={new QueryClient()}><ActiveStudyTime userId={7} lessonId={31} /></QueryClientProvider>)
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'performance'] })
  vi.spyOn(document, 'hasFocus').mockReturnValue(true)
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
  gate.online = true; gate.user = 7
  post.mockImplementation(async (url, { body }) => ({ response: { status: 200 }, data: url.endsWith('/sessions')
    ? { session_id: body.session_id, started_at: '2026-10-14T12:00:00Z', server_now: '2026-10-14T12:00:00Z' }
    : { operation_key: body.operation_key, credited_ms: body.duration_ms } }))
})
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); post.mockReset(); localStorage.clear() })

it('sem interação não registra tempo; atividade gera blocos e saída remove timers', async () => {
  let view!: ReturnType<typeof mount>
  await act(async () => { view = mount() })
  await act(async () => { await vi.advanceTimersByTimeAsync(60000) })
  expect(events()).toHaveLength(0)
  fireEvent.keyDown(window, { key: 'a' })
  await act(async () => { await vi.advanceTimersByTimeAsync(16000) })
  expect(events()).toHaveLength(1)
  expect(events()[0]![1].body.duration_ms).toBe(15000)
  expect(JSON.stringify(events())).not.toContain('keyDown')
  view.unmount()
  expect(vi.getTimerCount()).toBe(0)
})
it('ocultar ou abandonar a aba interrompe a contagem', async () => {
  await act(async () => { mount() })
  fireEvent.pointerDown(window)
  await act(async () => { await vi.advanceTimersByTimeAsync(16000) })
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
  fireEvent(document, new Event('visibilitychange'))
  const count = events().length
  await act(async () => { await vi.advanceTimersByTimeAsync(1800000) })
  expect(events()).toHaveLength(count)
})
it('offline mantém eventos e reconecta com a mesma chave; não envia para outra conta', async () => {
  await act(async () => { mount() })
  gate.online = false
  fireEvent.pointerDown(window)
  await act(async () => { await vi.advanceTimersByTimeAsync(16000) })
  expect(events()).toHaveLength(0)
  expect(savedEvents()).toHaveLength(1)
  const key = savedEvents()[0]!, body = JSON.parse(localStorage.getItem(key)!)
  gate.online = true; gate.user = 8
  await act(async () => { fireEvent(window, new Event('online')) })
  expect(events()).toHaveLength(0)
  expect(localStorage.getItem(key)).not.toBeNull()
  gate.user = 7
  await act(async () => { fireEvent(window, new Event('online')) })
  expect(events()[0]![1].body).toEqual(body)
  expect(savedEvents()).toHaveLength(0)
})
it('resposta perdida preserva evento e retry não cria outra chave', async () => {
  await act(async () => { mount() })
  const implementation = post.getMockImplementation()!
  post.mockImplementationOnce(async () => { throw new Error('resposta perdida') })
  fireEvent.keyDown(window)
  await act(async () => { await vi.advanceTimersByTimeAsync(16000) })
  expect(savedEvents()).toHaveLength(1)
  expect(screen.getByRole('status')).toHaveTextContent('pendente')
  post.mockImplementation(implementation)
  await act(async () => { fireEvent(window, new Event('online')) })
  expect(events()[1]![1].body).toEqual(events()[0]![1].body)
  expect(savedEvents()).toHaveLength(0)
})

it('abandono por cinco minutos conta no máximo a tolerância de dois minutos', async () => {
  await act(async () => { mount() })
  fireEvent.pointerDown(window)
  await act(async () => { await vi.advanceTimersByTimeAsync(300000) })
  const credited = events().reduce((total, [, { body }]) => total + body.duration_ms, 0)
  expect(credited).toBeGreaterThan(0)
  expect(credited).toBeLessThanOrEqual(120000)
  const count = events().length
  await act(async () => { await vi.advanceTimersByTimeAsync(300000) })
  expect(events()).toHaveLength(count)
})
