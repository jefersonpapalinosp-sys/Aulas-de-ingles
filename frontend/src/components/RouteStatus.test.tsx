import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useNavigate } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { RouteStatus } from './RouteStatus'

function Harness() {
  const navigate = useNavigate()
  return (
    <>
      <button type="button" onClick={() => navigate('/cursos/voa-level-1/aulas/31/exercicios')}>
        Abrir exercícios
      </button>
      <main id="main-content" tabIndex={-1}>
        <RouteStatus />
      </main>
    </>
  )
}

describe('RouteStatus', () => {
  it('atualiza título, anúncio e foco após a navegação interna', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/inicio']}>
        <Harness />
      </MemoryRouter>,
    )

    const main = screen.getByRole('main')
    await waitFor(() => expect(main).toHaveFocus())
    expect(document.title).toBe('Hoje | Aulas de Inglês')
    expect(screen.getByRole('status')).toHaveTextContent('Hoje carregada.')

    await user.click(screen.getByRole('button', { name: 'Abrir exercícios' }))

    await waitFor(() => expect(main).toHaveFocus())
    expect(document.title).toBe('Exercícios da Aula 31 | Aulas de Inglês')
    expect(screen.getByRole('status')).toHaveTextContent('Exercícios da Aula 31 carregada.')
  })
})
