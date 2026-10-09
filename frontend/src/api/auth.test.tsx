import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { StrictMode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SessaoProvider, useSessao } from './auth'

const { post, get, setAccessToken } = vi.hoisted(() => ({
  post: vi.fn(),
  get: vi.fn(),
  setAccessToken: vi.fn(),
}))

vi.mock('./client', () => ({
  api: { POST: post, GET: get },
  setAccessToken,
  // Registrado pelo provider para saber quando o refresh falhou de vez.
  onSessaoPerdida: vi.fn(),
}))

function EstadoDaSessao() {
  const { usuario, carregando, offline } = useSessao()
  if (carregando) return <p>carregando</p>
  return <p>{usuario ? `${usuario.display_name}${offline ? ' · offline' : ''}` : 'sem sessão'}</p>
}

afterEach(() => {
  localStorage.clear()
  vi.resetAllMocks()
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
})

describe('SessaoProvider', () => {
  it('faz uma única renovação inicial mesmo sob StrictMode', async () => {
    post.mockResolvedValue({ data: { access_token: 'access', expires_in: 900 } })
    get.mockResolvedValue({
      data: { id: 7, email: 'aluno@example.com', display_name: 'Aluno' },
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <StrictMode>
        <QueryClientProvider client={queryClient}>
          <SessaoProvider>
            <EstadoDaSessao />
          </SessaoProvider>
        </QueryClientProvider>
      </StrictMode>,
    )

    expect(await screen.findByText('Aluno')).toBeInTheDocument()
    expect(post).toHaveBeenCalledTimes(1)
    expect(post).toHaveBeenCalledWith('/api/auth/refresh')
    expect(setAccessToken).toHaveBeenCalledWith('access')
    await waitFor(() => expect(get).toHaveBeenCalledWith('/api/auth/me'))
  })

  it('restaura somente o perfil mínimo quando a rede está indisponível', async () => {
    localStorage.setItem(
      'aulas:last-user:v1',
      JSON.stringify({ id: 7, display_name: 'Aluno' }),
    )
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
    post.mockResolvedValue({ data: undefined, response: undefined })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={queryClient}>
        <SessaoProvider>
          <EstadoDaSessao />
        </SessaoProvider>
      </QueryClientProvider>,
    )

    expect(await screen.findByText('Aluno · offline')).toBeInTheDocument()
    expect(setAccessToken).not.toHaveBeenCalled()
    expect(get).not.toHaveBeenCalled()
  })
})
