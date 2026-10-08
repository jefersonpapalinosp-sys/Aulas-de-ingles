import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { NotebookPage } from './NotebookPage'

const clientMocks = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
  PUT: vi.fn(),
  DELETE: vi.fn(),
  authenticatedFetch: vi.fn(),
}))
const queryHooks = vi.hoisted(() => ({
  useCourses: vi.fn(),
  useCourseCurriculum: vi.fn(),
}))

const course = {
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
  published_lessons: 49,
}

vi.mock('../api/queries', () => ({
  useCourses: queryHooks.useCourses,
  useCourseCurriculum: queryHooks.useCourseCurriculum,
}))

vi.mock('../api/client', () => ({
  api: {
    GET: clientMocks.GET,
    POST: clientMocks.POST,
    PUT: clientMocks.PUT,
    DELETE: clientMocks.DELETE,
  },
  authenticatedFetch: clientMocks.authenticatedFetch,
}))

const lesson = {
  id: 45,
  course_slug: 'voa-level-1',
  unit_slug: '45-49',
  slug: 'lesson-45',
  position: 1,
  number: 45,
  title: 'This Land is Your Land',
  title_pt: 'Esta terra é sua terra',
  grammar_tag: 'Present perfect',
  focus_points: ['present perfect'],
  story_note: null,
}

const entry = {
  id: 8,
  course_slug: 'voa-level-1',
  course_title: course.title,
  unit_slug: '45-49',
  lesson_number: 45,
  lesson_title: lesson.title,
  kind: 'favorite_phrase' as const,
  content: 'A taxi is faster than a bus.',
  created_at: '2026-10-08T00:30:00Z',
  updated_at: '2026-10-08T00:30:00Z',
}

function mockQueries(entries = [entry]) {
  clientMocks.GET.mockImplementation(async (path) => {
    if (path === '/api/me/notebook') return { data: entries }
    if (path === '/api/speaking/attempts') return { data: [] }
    if (path === '/api/writing/history') {
      return {
        data: [
          {
            prompt_id: 4,
            course_slug: 'voa-level-1',
            course_title: course.title,
            unit_slug: '45-49',
            lesson_number: 45,
            lesson_title: lesson.title,
            prompt_title: 'Compare caminhos',
            draft_text: 'The train is faster.',
            updated_at: '2026-10-08T00:30:00Z',
            revisions: [{ id: 3, version: 1, text: 'The train is fast.', created_at: '2026-10-08T00:20:00Z' }],
            feedbacks: [],
          },
        ],
      }
    }
    return { data: undefined }
  })
}

function renderNotebook(route = '/caderno?course=voa-level-1&unit=45-49') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <NotebookPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  vi.clearAllMocks()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

function mockCurriculum() {
  queryHooks.useCourses.mockReturnValue({ data: [course], isPending: false, error: null })
  queryHooks.useCourseCurriculum.mockReturnValue({
    data: {
      course,
      units: [
        {
          id: 4,
          slug: '45-49',
          title: 'Aulas 45–49',
          position: 4,
          status: 'published',
          lesson_start: 45,
          lesson_end: 49,
          total_lessons: 5,
          published_lessons: 1,
          lessons: [lesson],
          review: null,
        },
      ],
    },
    isPending: false,
    error: null,
  })
}

describe('NotebookPage', () => {
  it('cria, edita e exclui uma anotação privada', async () => {
    const user = userEvent.setup()
    mockCurriculum()
    mockQueries()
    clientMocks.POST.mockResolvedValue({ data: { ...entry, id: 9, kind: 'note', content: 'New note' } })
    clientMocks.PUT.mockResolvedValue({ data: { ...entry, content: 'Frase atualizada.' } })
    clientMocks.DELETE.mockResolvedValue({ response: { ok: true } })
    renderNotebook()

    expect(await screen.findByText('A taxi is faster than a bus.')).toBeInTheDocument()
    expect(screen.getByText('Compare caminhos')).toBeInTheDocument()
    const editor = screen.getByRole('textbox', { name: 'Conteúdo' })
    await user.type(editor, 'New note')
    await user.click(screen.getByRole('button', { name: 'Salvar no caderno' }))
    await waitFor(() => expect(clientMocks.POST).toHaveBeenCalled())
    expect(clientMocks.POST).toHaveBeenCalledWith('/api/me/notebook', {
      body: {
        course_slug: 'voa-level-1',
        lesson_number: 45,
        kind: 'note',
        content: 'New note',
      },
    })

    expect(clientMocks.GET).toHaveBeenCalledWith('/api/me/notebook', {
      params: {
        query: {
          lesson: undefined,
          kind: undefined,
          course: 'voa-level-1',
          unit: '45-49',
        },
      },
    })
    expect(screen.getAllByText(/Let's Learn English — Level 1 · Aula 45/).length).toBeGreaterThan(0)
    expect(screen.getByRole('link', { name: 'Abrir texto' })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/aulas/45/estudar/revisar',
    )

    await user.click(screen.getByRole('button', { name: 'Editar' }))
    const editBox = screen.getByRole('textbox', { name: 'Conteúdo da anotação' })
    await user.clear(editBox)
    await user.type(editBox, 'Frase atualizada.')
    await user.click(screen.getByRole('button', { name: 'Salvar alteração' }))
    await waitFor(() => expect(clientMocks.PUT).toHaveBeenCalled())

    await user.click(screen.getByRole('button', { name: 'Excluir' }))
    expect(clientMocks.DELETE).toHaveBeenCalledWith('/api/me/notebook/{entry_id}', {
      params: { path: { entry_id: 8 } },
    })
  })

  it('baixa a exportação JSON do aluno', async () => {
    const user = userEvent.setup()
    mockCurriculum()
    mockQueries([])
    const blob = new Blob(['{"schema_version":"1.0"}'], { type: 'application/json' })
    clientMocks.authenticatedFetch.mockResolvedValue({ ok: true, blob: async () => blob })
    const createObjectURL = vi.fn().mockReturnValue('blob:export')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    renderNotebook()

    await user.click(await screen.findByRole('button', { name: 'Exportar meus dados' }))
    expect(clientMocks.authenticatedFetch).toHaveBeenCalledWith('/api/me/export')
    expect(createObjectURL).toHaveBeenCalledWith(blob)
    expect(click).toHaveBeenCalledOnce()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:export')
    expect(await screen.findByText(/Exportação preparada/)).toBeInTheDocument()
  })
})
