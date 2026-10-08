import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LoginPage } from './LoginPage'

const entrar = vi.fn()
const registrar = vi.fn()

vi.mock('../api/auth', () => ({
  useSessao: () => ({ entrar, registrar, usuario: null, carregando: false, sair: vi.fn() }),
}))

beforeEach(() => {
  window.scrollTo = vi.fn()
})

afterEach(() => vi.resetAllMocks())

describe('LoginPage', () => {
  it('entra com e-mail e senha', async () => {
    const user = userEvent.setup()
    entrar.mockResolvedValue(undefined)
    render(<LoginPage />)

    await user.type(screen.getByLabelText('E-mail'), 'jeferson@exemplo.com')
    await user.type(screen.getByLabelText('Senha'), 'senha-bem-grande')
    await user.click(screen.getByRole('button', { name: 'Entrar' }))

    expect(entrar).toHaveBeenCalledWith('jeferson@exemplo.com', 'senha-bem-grande')
  })

  it('mostra a mensagem que a API devolveu, não uma genérica', async () => {
    const user = userEvent.setup()
    entrar.mockRejectedValue(new Error('E-mail ou senha incorretos.'))
    render(<LoginPage />)

    await user.type(screen.getByLabelText('E-mail'), 'x@y.com')
    await user.type(screen.getByLabelText('Senha'), 'senha-bem-grande')
    await user.click(screen.getByRole('button', { name: 'Entrar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('E-mail ou senha incorretos.')
  })

  it('alterna para criar conta e pede o nome', async () => {
    const user = userEvent.setup()
    render(<LoginPage />)
    expect(screen.queryByLabelText('Nome')).toBeNull()

    await user.click(screen.getByRole('button', { name: 'Ainda não tenho conta' }))
    expect(screen.getByLabelText('Nome')).toBeInTheDocument()
    expect(screen.getByLabelText('Nome')).toHaveFocus()
    expect(window.scrollTo).toHaveBeenCalledWith({ top: 0, left: 0 })
    expect(screen.getByText('No mínimo 8 caracteres.')).toBeInTheDocument()
  })
})
