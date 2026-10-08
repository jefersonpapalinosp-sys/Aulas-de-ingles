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

let lessonFixture = lesson

vi.mock('../api/queries', () => ({
  useLesson: () => ({ data: lessonFixture, isPending: false, error: null, refetch: vi.fn() }),
  useCourseCurriculum: () => ({
    data: {
      course: { title: "VOA Let's Learn English — Level 1" },
      units: [
        {
          slug: '31-40',
          lessons: [
            {
              id: 31,
              number: 31,
              position: 1,
              title: lesson.title,
            },
          ],
          review: {
            id: 12,
            slug: 'checkpoint-31-40',
            position: 2,
            title: 'Checkpoint 31–40',
            status: 'published',
            estimated_minutes: 12,
            question_count: 6,
            review_lesson_number: 31,
            source_kind: 'mixed',
          },
        },
      ],
    },
  }),
}))

function renderLesson() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/cursos/voa-level-1/aulas/31']}>
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

  it('leva a última aula da unidade ao checkpoint curricular', () => {
    renderLesson()

    expect(screen.getByRole('link', { name: 'Checkpoint 31–40 →' })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/unidades/31-40/checkpoint',
    )
  })
})
