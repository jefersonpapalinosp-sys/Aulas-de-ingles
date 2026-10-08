import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MapPage } from './MapPage'

const savePlan = vi.fn()

vi.mock('../api/queries', () => ({
  useLessons: () => ({
    data: [
      {
        number: 31,
        title: 'Take Me Out to the Ball Game',
        grammar_tag: 'Comparativos',
        story_note: 'Transportation',
      },
    ],
    isPending: false,
    error: null,
    refetch: vi.fn(),
  }),
}))

vi.mock('../api/dashboard', () => ({
  useToday: () => ({
    data: {
      recommendation: {
        kind: 'continue_lesson',
        title: 'Continuar a Aula 31',
        reason: 'Você parou na etapa assistir; retomar preserva o contexto.',
        href: '/aulas/31/estudar/assistir',
        estimated_minutes: 10,
        lesson_number: 31,
      },
      plan: {
        weekly_minutes: 90,
        preferred_days: ['mon', 'wed', 'fri'],
        goal: 'Criar constância no inglês',
        updated_at: null,
      },
      recorded_minutes_this_week: 18,
      recent_session: {
        lesson_number: 31,
        lesson_title: 'Take Me Out to the Ball Game',
        current_step: 'assistir',
        completed_steps: 1,
        total_minutes: 18,
        updated_at: '2026-10-08T00:00:00Z',
      },
    },
    isPending: false,
    error: null,
    refetch: vi.fn(),
  }),
  useSkills: () => ({
    data: [
      {
        skill: 'grammar',
        label: 'Gramática',
        samples: 2,
        score_percent: null,
        status: 'insufficient',
        fragile_topics: ['Comparativos'],
      },
      {
        skill: 'listening',
        label: 'Compreensão oral',
        samples: 5,
        score_percent: 80,
        status: 'steady',
        fragile_topics: [],
      },
    ],
    isPending: false,
    error: null,
    refetch: vi.fn(),
  }),
  useSaveStudyPlan: () => ({
    mutate: savePlan,
    isPending: false,
    isSuccess: false,
    isError: false,
  }),
}))

describe('MapPage / painel Hoje', () => {
  beforeEach(() => savePlan.mockReset())

  it('explica a recomendação e esconde percentual com pouca amostra', () => {
    render(<MapPage />, { wrapper: MemoryRouter })

    expect(screen.getByRole('heading', { name: 'Hoje' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Continuar a Aula 31' })).toBeInTheDocument()
    expect(screen.getByText(/retomar preserva o contexto/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Estudar agora' })).toHaveAttribute(
      'href',
      '/aulas/31/estudar/assistir',
    )
    const grammar = screen.getByText('Gramática').closest('li')
    expect(grammar).not.toBeNull()
    expect(within(grammar!).getByText('Dados insuficientes (2/3)')).toBeInTheDocument()
    expect(within(grammar!).queryByText(/%/)).not.toBeInTheDocument()
    expect(screen.getByText('80%')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Mapa do bloco 31–40' })).toBeInTheDocument()
  })

  it('permite editar a meta sem bloquear o mapa', async () => {
    const user = userEvent.setup()
    render(<MapPage />, { wrapper: MemoryRouter })

    await user.clear(screen.getByLabelText('Meta'))
    await user.type(screen.getByLabelText('Meta'), 'Inglês para viagem')
    await user.clear(screen.getByLabelText('Minutos por semana'))
    await user.type(screen.getByLabelText('Minutos por semana'), '120')
    await user.click(screen.getByText('Qua'))
    await user.click(screen.getByText('Sáb'))
    await user.click(screen.getByRole('button', { name: 'Salvar plano' }))

    expect(savePlan).toHaveBeenCalledWith({
      weekly_minutes: 120,
      preferred_days: ['mon', 'fri', 'sat'],
      goal: 'Inglês para viagem',
    })
    expect(screen.getByRole('link', { name: /Take Me Out/ })).toBeInTheDocument()
  })
})
