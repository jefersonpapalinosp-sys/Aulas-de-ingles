import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

afterEach(() => {
  vi.restoreAllMocks()
})

function mockFetch(body: unknown, ok = true, status = 200) {
  return vi.spyOn(globalThis, 'fetch').mockResolvedValue({
    ok,
    status,
    json: async () => body,
  } as Response)
}

describe('App', () => {
  it('mostra o estado vindo da API, não um valor fixo', async () => {
    mockFetch({ status: 'ok', db: 'up', version: 'PostgreSQL 16.4', env: 'dev' })
    render(<App />)
    await waitFor(() => expect(screen.getByText('PostgreSQL 16.4')).toBeInTheDocument())
    expect(screen.getByText('up')).toBeInTheDocument()
  })

  it('mostra erro com instrução quando a API não responde', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('network'))
    render(<App />)
    await waitFor(() =>
      expect(screen.getByText(/Não foi possível falar com a API/)).toBeInTheDocument(),
    )
    expect(screen.getByText(/make up/)).toBeInTheDocument()
  })

  it('reflete banco fora do ar sem travar a tela', async () => {
    mockFetch({ status: 'degraded', db: 'down', version: null, env: 'dev' }, false, 503)
    render(<App />)
    await waitFor(() => expect(screen.getByText('down')).toBeInTheDocument())
    expect(screen.getByText('degraded')).toBeInTheDocument()
  })
})
