import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MapPage } from './MapPage'

const savePlan = vi.fn()

const lesson = {
  id: 31,
  course_slug: 'voa-level-1',
  unit_slug: '31-40',
  slug: 'take-me-out-to-the-ball-game',
  position: 1,
  number: 31,
  title: 'Take Me Out to the Ball Game',
  title_pt: 'Leve-me ao jogo',
  grammar_tag: 'Comparativos',
  focus_points: ['faster than'],
  story_note: 'Transportation',
}

vi.mock('../api/queries', () => ({
  useCourseCurriculum: () => ({
    data: {
      course: {
        id: 1,
        slug: 'voa-level-1',
        title: "Let's Learn English — Level 1",
        level: 'Level 1',
        proficiency_label: 'Iniciante',
        provider: 'VOA Learning English',
        source_url: 'https://example.com',
        position: 1,
        status: 'published',
        total_lessons: 52,
        published_lessons: 10,
      },
      units: [
        {
          id: 1,
          slug: '31-40',
          title: 'Unidade 31–40',
          position: 1,
          status: 'published',
          lesson_start: 31,
          lesson_end: 40,
          total_lessons: 10,
          published_lessons: 1,
          lessons: [lesson],
        },
      ],
    },
    isPending: false,
    error: null,
    refetch: vi.fn(),
  }),
}))

vi.mock('../api/progress', () => ({
  useProgress: () => ({
    data: {
      studied_count: 0,
      total_lessons: 1,
      attempts: 0,
      correct: 0,
      review_due: 0,
      review_cards: 0,
      lessons: [
        {
          course_slug: 'voa-level-1',
          unit_slug: '31-40',
          lesson_number: 31,
          studied: false,
          studied_at: null,
          attempts: 0,
          correct: 0,
        },
      ],
    },
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

  it('explica a recomendação e converte o link antigo para a rota canônica', () => {
    render(<MapPage showToday />, { wrapper: MemoryRouter })

    expect(screen.getByRole('heading', { name: 'Hoje' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Continuar a Aula 31' })).toBeInTheDocument()
    expect(screen.getByText(/retomar preserva o contexto/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Estudar agora' })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/aulas/31/estudar/assistir',
    )
    const grammar = screen.getByText('Gramática').closest('li')
    expect(grammar).not.toBeNull()
    expect(within(grammar!).getByText('Dados insuficientes (2/3)')).toBeInTheDocument()
    expect(within(grammar!).queryByText(/%/)).not.toBeInTheDocument()
    expect(screen.getByText('80%')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Mapa do curso' })).toBeInTheDocument()
  })

  it('permite editar a meta sem bloquear o catálogo de unidades', async () => {
    const user = userEvent.setup()
    render(<MapPage showToday />, { wrapper: MemoryRouter })

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
    expect(screen.getByRole('link', { name: /Unidade 31–40/ })).toBeInTheDocument()
  })
})
