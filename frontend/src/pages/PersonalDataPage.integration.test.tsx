import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { setAccessToken, setSessionReadOnly, setSessionUser } from '../api/client'
import { PersonalDataPage } from './PersonalDataPage'

const ended = vi.hoisted(() => vi.fn())
vi.mock('../api/auth', () => ({ useSessao: () => ({ usuario: { id: 7 }, offline: false, encerrarContaExcluida: ended }) }))

afterEach(() => {
  cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); ended.mockReset()
  setAccessToken(null); setSessionUser(null); setSessionReadOnly(false)
})

it.each([202, 403])('exclusão atravessa o transporte autenticado até fetch: HTTP %s', async (status) => {
  setSessionUser(7); setSessionReadOnly(false); setAccessToken('synthetic-access-token')
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  const fetcher = vi.fn(async (input: RequestInfo | URL) => {
    expect(input).toBeInstanceOf(Request)
    const request = input as Request
    expect(new URL(request.url).pathname).toBe('/api/me/account')
    expect(request.method).toBe('DELETE')
    expect(request.credentials).toBe('same-origin')
    expect(request.cache).toBe('no-store')
    expect(request.headers.get('Authorization')).toBe('Bearer synthetic-access-token')
    expect(await request.json()).toEqual({
      password: 'senha-bem-grande', confirmation: 'EXCLUIR MINHA CONTA',
      operation_key: expect.stringMatching(/^[0-9a-f-]{36}$/) as unknown,
    })
    return new Response(JSON.stringify(status === 202
      ? { database_deleted: true, state: 'completed' } : { code: 'password_mismatch' }), { status })
  })
  vi.stubGlobal('fetch', fetcher)
  render(<MemoryRouter><PersonalDataPage /></MemoryRouter>)
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Senha atual'), 'senha-bem-grande')
  await user.type(screen.getByLabelText('Digite EXCLUIR MINHA CONTA'), 'EXCLUIR MINHA CONTA')
  await user.click(screen.getByRole('button', { name: 'Excluir minha conta definitivamente' }))
  if (status === 202) await waitFor(() => expect(ended).toHaveBeenCalledWith(false))
  else {
    expect(await screen.findByRole('alert')).toHaveTextContent('Senha incorreta')
    expect(ended).not.toHaveBeenCalled()
  }
  expect(fetcher).toHaveBeenCalledTimes(1)
})
