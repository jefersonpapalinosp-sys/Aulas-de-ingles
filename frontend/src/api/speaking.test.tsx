import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { afterEach, expect, it, vi } from 'vitest'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('transcrição distingue desativação permanente, cota e falha transitória através do fetch', async () => {
  const NativeRequest = Request
  // O browser resolve URLs relativas; o Request nativo do Node exige base absoluta.
  vi.stubGlobal('Request', class extends NativeRequest {
    constructor(input: RequestInfo | URL, init?: RequestInit) {
      super(typeof input === 'string' ? new URL(input, window.location.href) : input, init)
    }
  })
  const replies = [
    { status: 409, body: { detail: { code: 'assist_disabled' } } },
    { status: 429, body: { detail: 'quota' } },
    { status: 503, body: { detail: 'temporary' } },
    { status: 202, body: { id: 9, status: 'queued' } },
  ]
  const fetcher = vi.fn((request: Request) => {
    expect(request.headers.get('Authorization')).toBe('Bearer synthetic-speaking')
    if (request.method === 'GET') return Promise.resolve(Response.json([]))
    expect(new URL(request.url).pathname).toBe('/api/speaking/attempts/7/transcription')
    const next = replies.shift()
    if (!next) throw new Error('Reenvio inesperado')
    return Promise.resolve(Response.json(next.body, { status: next.status }))
  })
  vi.stubGlobal('fetch', fetcher)
  const { setSessionUser, setAccessToken } = await import('./session')
  setSessionUser(7); setAccessToken('synthetic-speaking')
  const { useSpeakingHistory } = await import('./speaking')
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  const announce = vi.fn()
  const { result, unmount } = renderHook(() => useSpeakingHistory(7, 'voa-level-1', 31, announce), { wrapper })
  await waitFor(() => expect(result.current.query.isSuccess).toBe(true))
  for (const message of ['desativada nesta instalação', 'cota diária', 'provedor não está disponível', 'Transcrição solicitada']) {
    await act(() => result.current.transcribe(7))
    expect(announce).toHaveBeenLastCalledWith(expect.stringContaining(message))
  }
  expect(replies).toHaveLength(0)
  expect(fetcher.mock.calls.filter(([r]) => r.method === 'POST')).toHaveLength(4)
  unmount(); client.clear(); setSessionUser(null); setAccessToken(null)
})
