import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { TestPage } from './TestPage'

const hooks = vi.hoisted(() => ({
  useAllExercises: vi.fn(),
  useCourseCurriculum: vi.fn(),
}))

vi.mock('../api/auth', () => ({
  useSessao: () => ({ usuario: { id: 7, display_name: 'Aluno' } }),
}))

vi.mock('../api/queries', () => ({
  useAllExercises: hooks.useAllExercises,
  useCourseCurriculum: hooks.useCourseCurriculum,
}))

vi.mock('../components/ExerciseCard', () => ({
  ExerciseCard: ({
    exercicio,
    aoResponder,
  }: {
    exercicio: { id: number; prompt: string }
    aoResponder?: (correct: boolean) => void
  }) => (
    <button type="button" onClick={() => aoResponder?.(true)}>
      {exercicio.prompt}
    </button>
  ),
}))

const unit = {
  id: 3,
  slug: '45-49',
  title: 'Aulas 45–49',
  position: 3,
  status: 'published',
  lesson_start: 45,
  lesson_end: 49,
  total_lessons: 5,
  published_lessons: 5,
  lessons: [],
  review: null,
}

const exercise = {
  id: 1,
  course_slug: 'voa-level-1',
  unit_slug: '45-49',
  lesson_number: 45,
  position: 1,
  activity_type: 'multiple_choice',
  objective: 'recognize',
  skill: 'grammar',
  prompt: 'Questão da Aula 45',
  options: ['A', 'B'],
  hint_count: 0,
  hint: null,
  explanation: null,
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/cursos/voa-level-1/unidades/45-49/avaliacao']}>
      <Routes>
        <Route
          path="/cursos/:courseSlug/unidades/:unitSlug/avaliacao"
          element={<TestPage />}
        />
      </Routes>
    </MemoryRouter>,
  )
}

describe('TestPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    hooks.useCourseCurriculum.mockReturnValue({
      data: {
        course: { title: "Let's Learn English — Level 1" },
        units: [unit],
      },
      isPending: false,
      error: null,
      refetch: vi.fn(),
    })
    hooks.useAllExercises.mockReturnValue({
      data: [
        exercise,
        { ...exercise, id: 2, position: 2, prompt: 'Segunda questão da Aula 45' },
        {
          ...exercise,
          id: 3,
          course_slug: 'voa-level-2',
          prompt: 'Mesma numeração em outro curso',
        },
      ],
      isPending: false,
      error: null,
      refetch: vi.fn(),
    })
  })

  it('consulta pelo curso e unidade e deduplica pela identidade composta', async () => {
    const user = userEvent.setup()
    renderPage()

    expect(hooks.useAllExercises).toHaveBeenCalledWith('voa-level-1', '45-49')
    expect(screen.getByRole('heading', { name: 'Avaliação da unidade' })).toBeInTheDocument()
    expect(screen.getByText(/Aulas 45–49/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Questão da Aula 45' })).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Mesma numeração em outro curso' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Segunda questão da Aula 45' }),
    ).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Questão da Aula 45' }))
    expect(screen.getByText('1/1')).toBeInTheDocument()
  })

  it('explica quando a unidade ainda não possui exercícios publicados', () => {
    hooks.useAllExercises.mockReturnValue({
      data: [],
      isPending: false,
      error: null,
      refetch: vi.fn(),
    })
    renderPage()

    expect(screen.getByRole('note')).toHaveTextContent('Avaliação em preparação')
    expect(screen.getByRole('link', { name: 'Voltar à unidade' })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/unidades/45-49',
    )
  })
})
