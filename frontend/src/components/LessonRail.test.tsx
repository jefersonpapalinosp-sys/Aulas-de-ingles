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
    published_lessons: 15,
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
      total_lessons: 15,
      attempts: 0,
      correct: 0,
      review_due: 2,
      review_cards: 2,
      lessons: [...firstUnitLessons, lesson(15, '15-20')].map((item) => ({
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

function renderRail() {
  return render(
    <MemoryRouter initialEntries={['/cursos/voa-level-1/aulas/14']}>
      <LessonRail />
    </MemoryRouter>,
  )
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
    const search = within(dialog).getByRole('searchbox', { name: 'Buscar aula' })
    await waitFor(() => expect(search).toHaveFocus())

    await user.type(search, 'não existe')
    expect(
      within(dialog).getByText('Nenhuma aula encontrada neste curso.'),
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
})
