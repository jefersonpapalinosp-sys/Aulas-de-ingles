import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { LessonPage } from './LessonPage'

const lesson = {
  id: 31,
  course_slug: 'voa-level-1',
  unit_slug: '31-40',
  slug: 'lesson-31',
  position: 1,
  number: 31,
  title: 'Take Me Out to the Ball Game',
  title_pt: 'Me leva pro jogo de beisebol',
  voa_url: 'https://example.com/31',
  grammar_tag: 'Comparativos',
  focus_points: ['-er ou more'],
  story_note: null,
  lead: 'Compare duas coisas.',
  goals: [],
  grammar_blocks: [],
  phrases: [],
  vocab: [],
  pronunciation: [],
  media: [],
  content_sources: [],
  versions: [],
  exercises: [{ id: 1 }, { id: 2 }],
}

const lessons31To40 = Array.from({ length: 10 }, (_, index) => {
  const number = 31 + index
  return {
    id: number,
    number,
    position: index + 1,
    title:
      number === 31
        ? 'Take Me Out to the Ball Game'
        : number === 40
          ? 'The Woods Are Alive'
          : `Lesson ${number}`,
  }
})

let lessonFixture = lesson

vi.mock('../api/queries', () => ({
  useLesson: () => ({ data: lessonFixture, isPending: false, error: null, refetch: vi.fn() }),
  useCourseCurriculum: () => ({
    data: {
      course: { title: "VOA Let's Learn English — Level 1" },
      units: [
        {
          slug: '31-40',
          lessons: lessons31To40,
          review: {
            id: 12,
            slug: 'checkpoint-31-40-level-1',
            position: 11,
            title: 'Fechamento 31–40',
            status: 'published',
            estimated_minutes: 18,
            question_count: 10,
            review_lesson_number: 40,
            source_kind: 'authorial',
          },
        },
        {
          slug: '40-44',
          lessons: [
            {
              id: 41,
              number: 41,
              position: 1,
              title: 'Teamwork Works Best With a Team',
            },
          ],
          review: {
            id: 41,
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
          slug: '50-52',
          lessons: [
            {
              id: 52,
              number: 52,
              position: 3,
              title: 'Taking Chances',
            },
          ],
          review: {
            id: 52,
            slug: 'checkpoint-50-52',
            position: 4,
            title: 'Checkpoint 50–52',
            status: 'published',
            estimated_minutes: 12,
            question_count: 6,
            review_lesson_number: 52,
            source_kind: 'mixed',
          },
        },
      ],
    },
  }),
}))

function renderLesson(route = '/cursos/voa-level-1/aulas/31') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/cursos/:courseSlug/aulas/:numero" element={<LessonPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  lessonFixture = lesson
})

describe('LessonPage', () => {
  it('substitui a lista longa de cards pelo resumo e CTA do laboratório', () => {
    renderLesson()

    expect(screen.getByText(/2 atividades com retomada/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Abrir laboratório' })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/aulas/31/exercicios',
    )
    expect(screen.queryByRole('textbox', { name: /Resposta do exercício/ })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Verificar' })).toBeNull()
  })

  it('mantém a entrada da jornada e omite seções vazias quando a aula ainda não tem mídia ou coleções', () => {
    lessonFixture = { ...lesson, exercises: [] }
    renderLesson()

    expect(
      screen.getByText(
        'Estude em cinco etapas; quando não houver mídia, use a alternativa textual.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Começar estudo' })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/aulas/31/estudar',
    )
    for (const heading of [
      'Objetivos da aula',
      'Gramática',
      'Frases da aula',
      'Vocabulário',
      'Pronúncia',
      'Exercícios',
    ]) {
      expect(screen.queryByRole('heading', { name: heading })).not.toBeInTheDocument()
    }
  })

  it('leva a Aula 40 ao fechamento curricular da unidade 31–40', () => {
    lessonFixture = {
      ...lesson,
      id: 40,
      slug: 'lesson-40',
      position: 10,
      number: 40,
      title: 'The Woods Are Alive',
    }
    renderLesson('/cursos/voa-level-1/aulas/40')

    expect(screen.getByRole('link', { name: 'Fechamento 31–40 →' })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/unidades/31-40/checkpoint',
    )
  })

  it('encadeia a Aula 52 ao checkpoint final do recorte', () => {
    lessonFixture = {
      ...lesson,
      id: 52,
      unit_slug: '50-52',
      slug: 'taking-chances',
      position: 3,
      number: 52,
      title: 'Taking Chances',
    }
    renderLesson('/cursos/voa-level-1/aulas/52')

    expect(screen.getByRole('link', { name: 'Checkpoint 50–52 →' })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/unidades/50-52/checkpoint',
    )
  })
})
