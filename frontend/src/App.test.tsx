import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import App from './App'

vi.mock('./api/auth', () => ({
  useSessao: () => ({
    usuario: { id: 7, email: 'aluno@example.com', display_name: 'Aluno' },
    carregando: false,
    offline: false,
  }),
}))

vi.mock('./components/LessonRail', () => ({
  LessonRail: () => <nav aria-label="Trilha de teste" />,
}))

vi.mock('./features/offline/ConnectivityStatus', () => ({
  ConnectivityStatus: () => null,
}))

vi.mock('./pages/CourseCompletionPage', () => ({
  CourseCompletionPage: () => <h1>Fechamento do curso carregado</h1>,
}))

describe('App', () => {
  // Desde a Sprint 30 as rotas pesadas são carregadas sob demanda, então a
  // página só aparece depois que o chunk resolve.
  it('expõe a conclusão pela rota canônica autenticada', async () => {
    render(
      <MemoryRouter initialEntries={['/cursos/voa-level-1/conclusao']}>
        <App />
      </MemoryRouter>,
    )

    expect(
      await screen.findByRole('heading', { name: 'Fechamento do curso carregado' }),
    ).toBeInTheDocument()
    expect(screen.queryByText('Página não encontrada')).not.toBeInTheDocument()
  })
})
