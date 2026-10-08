import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
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

vi.mock('../api/queries', () => ({
  useLesson: () => ({ data: lesson, isPending: false, error: null, refetch: vi.fn() }),
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
        },
      ],
    },
  }),
}))

describe('LessonPage', () => {
  it('substitui a lista longa de cards pelo resumo e CTA do laboratório', () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/cursos/voa-level-1/aulas/31']}>
          <Routes>
            <Route path="/cursos/:courseSlug/aulas/:numero" element={<LessonPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(screen.getByText(/2 atividades com retomada/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Abrir laboratório' })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/aulas/31/exercicios',
    )
    expect(screen.queryByRole('textbox', { name: /Resposta do exercício/ })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Verificar' })).toBeNull()
  })
})
