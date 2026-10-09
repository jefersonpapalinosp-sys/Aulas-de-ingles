import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
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

const unitLessons = Array.from({ length: 4 }, (_, index) => ({
  ...lesson,
  id: 41 + index,
  unit_slug: '40-44',
  slug: `lesson-${41 + index}`,
  position: index + 1,
  number: 41 + index,
  title: `Lesson ${41 + index}`,
  title_pt: `Aula ${41 + index}`,
  grammar_tag: 'Gramática da unidade',
}))
let studiedLessonNumbers: number[] = []
let courseStatus: 'planned' | 'published' = 'published'
let publishedLessonCount = 10
let requestedTodayCourse = ''

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
        status: courseStatus,
        total_lessons: 52,
        published_lessons: publishedLessonCount,
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
          review: null,
        },
        {
          id: 2,
          slug: '40-44',
          title: 'Unidade 40–44',
          position: 2,
          status: 'published',
          lesson_start: 40,
          lesson_end: 44,
          total_lessons: 4,
          published_lessons: 4,
          lessons: unitLessons,
          review: {
            id: 12,
            slug: 'checkpoint-40-44',
            position: 5,
            title: 'Checkpoint 40–44',
            status: 'published',
            estimated_minutes: 12,
            question_count: 6,
            review_lesson_number: 40,
            source_kind: 'mixed',
          },
        },
        {
          id: 3,
          slug: '45-49',
          title: 'Unidade 45–49',
          position: 3,
          status: 'planned',
          lesson_start: 45,
          lesson_end: 49,
          total_lessons: 5,
          published_lessons: 0,
          lessons: [],
          review: null,
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
      total_lessons: 5,
      attempts: 0,
      correct: 0,
      review_due: 0,
      review_cards: 0,
      lessons: [lesson, ...unitLessons].map((item) => ({
        course_slug: item.course_slug,
        unit_slug: item.unit_slug,
        lesson_number: item.number,
        studied: studiedLessonNumbers.includes(item.number),
        studied_at: studiedLessonNumbers.includes(item.number)
          ? '2026-10-08T00:00:00Z'
          : null,
        attempts: 0,
        correct: 0,
      })),
    },
  }),
}))

vi.mock('../api/dashboard', () => ({
  useToday: (courseSlug: string) => {
    requestedTodayCourse = courseSlug
    return {
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
        course_slug: 'voa-level-1',
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
    }
  },
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
  beforeEach(() => {
    savePlan.mockReset()
    studiedLessonNumbers = []
    courseStatus = 'published'
    publishedLessonCount = 10
    requestedTodayCourse = ''
  })

  it('explica a recomendação e converte o link antigo para a rota canônica', () => {
    render(<MapPage showToday />, { wrapper: MemoryRouter })

    expect(screen.getByRole('heading', { name: 'Hoje' })).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'Level 1 · Continuar a Aula 31' }),
    ).toBeInTheDocument()
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
    expect(screen.getByRole('link', { name: 'Ver meu fechamento' })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/conclusao',
    )
  })

  it('lê o curso ativo da URL do Hoje e explicita o nível nas referências de aula', () => {
    render(
      <MemoryRouter initialEntries={['/inicio?course=voa-level-2']}>
        <Routes>
          <Route path="/inicio" element={<MapPage showToday />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(requestedTodayCourse).toBe('voa-level-2')
    expect(
      screen.getByRole('heading', { name: 'Level 2 · Continuar a Aula 31' }),
    ).toBeInTheDocument()
    expect(screen.getByText(/Level 2 · Aula 31/)).toBeInTheDocument()
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

  it('não oferece fechamento para curso planejado sem aulas publicadas', () => {
    courseStatus = 'planned'
    publishedLessonCount = 0
    render(<MapPage />, { wrapper: MemoryRouter })

    expect(screen.queryByRole('link', { name: 'Ver meu fechamento' })).not.toBeInTheDocument()
  })

  it('mantém unidade planejada visível, mas fora da navegação', () => {
    render(<MapPage />, { wrapper: MemoryRouter })

    const planned = screen.getByRole('article', { name: 'Unidade 45–49: Em preparação' })
    expect(planned).toHaveAttribute('aria-disabled', 'true')
    expect(within(planned).getByText('5 aulas planejadas')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Unidade 45–49/ })).not.toBeInTheDocument()
  })

  it('explica uma URL direta de unidade planejada sem renderizar uma lista vazia', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/cursos/voa-level-1/unidades/45-49']}>
        <Routes>
          <Route path="/cursos/:courseSlug/unidades/:unitSlug" element={<MapPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { name: 'Unidade em preparação' })).toBeInTheDocument()
    expect(screen.getByText(/Aulas 45–49 ainda não estão publicadas/)).toBeInTheDocument()
    expect(container.querySelector('.course-unit-lessons')).not.toBeInTheDocument()
  })

  it('apresenta o checkpoint como item próprio no mapa da unidade', () => {
    render(
      <MemoryRouter
        initialEntries={['/cursos/voa-level-1/unidades/40-44']}
      >
        <Routes>
          <Route
            path="/cursos/:courseSlug/unidades/:unitSlug"
            element={<MapPage />}
          />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { name: 'Unidade 40–44' })).toBeInTheDocument()
    expect(screen.getByText(/4 aulas disponíveis e um checkpoint/)).toBeInTheDocument()
    const checkpoint = screen.getByRole('link', { name: /Checkpoint 40–44/ })
    expect(checkpoint).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/unidades/40-44/checkpoint',
    )
    expect(within(checkpoint).getByText(/6 questões · cerca de 12 min/)).toBeInTheDocument()
    expect(within(checkpoint).getByText('CP')).toBeInTheDocument()
    expect(checkpoint).not.toHaveTextContent('✓')
  })

  it('distingue aulas concluídas do estado ainda desconhecido do checkpoint', () => {
    studiedLessonNumbers = [41, 42, 43, 44]
    render(
      <MemoryRouter initialEntries={['/cursos/voa-level-1/unidades/40-44']}>
        <Routes>
          <Route
            path="/cursos/:courseSlug/unidades/:unitSlug"
            element={<MapPage />}
          />
        </Routes>
      </MemoryRouter>,
    )

    const unit = screen.getByRole('link', { name: /Unidade 40–44/ })
    expect(unit).toHaveTextContent('Aulas concluídas · checkpoint disponível')
    expect(unit).toHaveTextContent('4/4 aulas')
    expect(within(unit).queryByText(/^Concluída$/)).not.toBeInTheDocument()
  })
})
