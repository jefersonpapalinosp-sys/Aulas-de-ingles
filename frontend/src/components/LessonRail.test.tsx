import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CourseCurriculum, LessonSummary } from '../api/client'
import { LessonRail } from './LessonRail'

const markStudied = vi.fn()
const signOut = vi.fn()

function lesson(number: number, unitSlug: string): LessonSummary {
  return {
    id: number,
    course_slug: 'voa-level-1',
    unit_slug: unitSlug,
    slug: `lesson-${number}`,
    position: number,
    number,
    title: `Lesson ${number}`,
    title_pt: `Aula ${number}`,
    grammar_tag: number === 14 ? 'Present perfect' : 'Grammar',
    focus_points: [],
    story_note: null,
  }
}

const firstUnitLessons = Array.from({ length: 14 }, (_, index) =>
  lesson(index + 1, '1-14'),
)
const curriculum: CourseCurriculum = {
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
    published_lessons: 16,
  },
  units: [
    {
      id: 1,
      slug: '1-14',
      title: 'Unidade 1–14',
      position: 1,
      status: 'published',
      lesson_start: 1,
      lesson_end: 14,
      total_lessons: 14,
      published_lessons: 14,
      lessons: firstUnitLessons,
      review: null,
    },
    {
      id: 2,
      slug: '15-20',
      title: 'Unidade 15–20',
      position: 2,
      status: 'published',
      lesson_start: 15,
      lesson_end: 20,
      total_lessons: 6,
      published_lessons: 1,
      lessons: [lesson(15, '15-20')],
      review: null,
    },
    {
      id: 3,
      slug: '40-44',
      title: 'Unidade 40–44',
      position: 3,
      status: 'published',
      lesson_start: 40,
      lesson_end: 44,
      total_lessons: 4,
      published_lessons: 1,
      lessons: [lesson(41, '40-44')],
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
  ],
}

vi.mock('../api/auth', () => ({
  useSessao: () => ({
    usuario: { id: 7, email: 'student@example.com', display_name: 'Student' },
    sair: signOut,
  }),
}))

vi.mock('../api/queries', () => ({
  useCourses: () => ({
    data: [curriculum.course],
    isPending: false,
    error: null,
  }),
  useCourseCurriculum: () => ({
    data: curriculum,
    isPending: false,
    error: null,
  }),
}))

vi.mock('../api/progress', () => ({
  useProgress: () => ({
    data: {
      studied_count: 1,
      total_lessons: 16,
      attempts: 0,
      correct: 0,
      review_due: 2,
      review_cards: 2,
      lessons: [...firstUnitLessons, lesson(15, '15-20'), lesson(41, '40-44')].map((item) => ({
        course_slug: item.course_slug,
        unit_slug: item.unit_slug,
        lesson_number: item.number,
        studied: item.number === 1,
        studied_at: item.number === 1 ? '2026-10-08T00:00:00Z' : null,
        attempts: 0,
        correct: 0,
      })),
    },
  }),
  useMarcarEstudada: () => ({
    mutate: markStudied,
    isPending: false,
  }),
}))

function renderRailAt(route = '/cursos/voa-level-1/aulas/14') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <LessonRail />
    </MemoryRouter>,
  )
}

function renderRail() {
  return renderRailAt()
}

describe('LessonRail', () => {
  beforeEach(() => {
    markStudied.mockReset()
    signOut.mockReset()
  })

  it('mantém uma unidade aberta e traz o deep link ativo para a janela de 12 aulas', async () => {
    const user = userEvent.setup()
    const { container } = renderRail()
    const desktop = container.querySelector<HTMLElement>('.rail')
    expect(desktop).not.toBeNull()

    const firstUnit = within(desktop!).getByRole('button', { name: /Unidade 1–14/ })
    const secondUnit = within(desktop!).getByRole('button', { name: /Unidade 15–20/ })
    await waitFor(() => expect(firstUnit).toHaveAttribute('aria-expanded', 'true'))
    expect(secondUnit).toHaveAttribute('aria-expanded', 'false')
    expect(within(desktop!).getByRole('link', { name: /Revisar/ })).toHaveAttribute(
      'href',
      '/revisar?course=voa-level-1&unit=1-14',
    )
    expect(within(desktop!).getByRole('link', { name: 'Caderno' })).toHaveAttribute(
      'href',
      '/caderno?course=voa-level-1&unit=1-14',
    )
    expect(within(desktop!).getByRole('link', { name: 'Avaliação' })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/unidades/1-14/avaliacao',
    )

    const lessonLinks = within(desktop!).getAllByRole('link', { name: /Lesson \d+/ })
    expect(lessonLinks.filter((link) => link.classList.contains('trail-lesson-link'))).toHaveLength(12)
    expect(within(desktop!).getByRole('link', { name: /Lesson 14/ })).toHaveAttribute(
      'aria-current',
      'page',
    )

    await user.click(secondUnit)
    expect(secondUnit).toHaveAttribute('aria-expanded', 'true')
    expect(firstUnit).toHaveAttribute('aria-expanded', 'false')
    expect(within(desktop!).getAllByRole('link', { name: /Lesson 15/ })).toHaveLength(1)
  })

  it('abre drawer com foco inicial, busca vazia e devolve foco ao fechar com Escape', async () => {
    const user = userEvent.setup()
    renderRail()
    const opener = screen.getByRole('button', { name: /Abrir trilha de aulas/ })

    await user.click(opener)
    const dialog = screen.getByRole('dialog', { name: 'Trilha de estudo' })
    const search = within(dialog).getByRole('searchbox', { name: 'Buscar aula ou checkpoint' })
    await waitFor(() => expect(search).toHaveFocus())

    await user.type(search, 'não existe')
    expect(
      within(dialog).getByText('Nenhuma aula ou checkpoint encontrado neste curso.'),
    ).toBeInTheDocument()

    fireEvent.keyDown(dialog, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await waitFor(() => expect(opener).toHaveFocus())
  })

  it('mantém o foco dentro do drawer ao retroceder do primeiro controle', async () => {
    const user = userEvent.setup()
    renderRail()
    await user.click(screen.getByRole('button', { name: /Abrir trilha de aulas/ }))
    const dialog = screen.getByRole('dialog', { name: 'Trilha de estudo' })
    const first = within(dialog).getByRole('button', { name: 'Fechar trilha' })
    first.focus()
    await user.tab({ shift: true })
    expect(dialog).toContainElement(document.activeElement as HTMLElement)
    expect(document.activeElement).not.toBe(first)
  })

  it('mostra o checkpoint no trilho e aponta para a rota da unidade', async () => {
    const user = userEvent.setup()
    const { container } = renderRail()
    const desktop = container.querySelector<HTMLElement>('.rail')
    expect(desktop).not.toBeNull()

    await user.click(within(desktop!).getByRole('button', { name: /Unidade 40–44/ }))
    const checkpoint = within(desktop!).getByRole('link', { name: /Checkpoint 40–44/ })

    expect(checkpoint).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/unidades/40-44/checkpoint',
    )
    expect(checkpoint).toHaveTextContent('6 questões · 12 min')
    expect(within(checkpoint).getByText('CP')).toBeInTheDocument()
    expect(checkpoint).not.toHaveTextContent('✓')
  })

  it('identifica o checkpoint no cabeçalho móvel da rota ativa', () => {
    renderRailAt('/cursos/voa-level-1/unidades/40-44/checkpoint')

    expect(screen.getByRole('button', { name: /Abrir trilha de aulas/ })).toHaveTextContent(
      'Checkpoint 40–44',
    )
  })

  it('preserva curso e unidade do escopo nas páginas utilitárias', async () => {
    const { container } = renderRailAt(
      '/revisar?course=voa-level-1&unit=40-44',
    )
    const desktop = container.querySelector<HTMLElement>('.rail')
    expect(desktop).not.toBeNull()

    await waitFor(() =>
      expect(
        within(desktop!).getByRole('button', { name: /Unidade 40–44/ }),
      ).toHaveAttribute('aria-expanded', 'true'),
    )
    expect(within(desktop!).getByRole('link', { name: /Revisar/ })).toHaveAttribute(
      'href',
      '/revisar?course=voa-level-1&unit=40-44',
    )
    expect(within(desktop!).getByRole('link', { name: 'Avaliação' })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/unidades/40-44/avaliacao',
    )
  })
})
