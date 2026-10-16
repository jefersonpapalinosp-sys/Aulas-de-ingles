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

function mockQueries(
  entries = [entry],
  feedbacks: unknown[] = [],
  nextCursor: string | null = null,
  nextEntries: typeof entries = [],
  nextWritingCursor: string | null = null,
  nextWritingEntries: Record<string, unknown>[] = [],
  speakingEntries: Record<string, unknown>[] = [],
  nextSpeakingCursor: string | null = null,
  nextSpeakingEntries: Record<string, unknown>[] = [],
) {
  clientMocks.GET.mockImplementation(async (path, options) => {
    if (path === '/api/me/notebook/page') {
      const cursor = options?.params?.query?.cursor
      return cursor
        ? { data: { items: nextEntries, next_cursor: null } }
        : { data: { items: entries, next_cursor: nextCursor } }
    }
    if (path === '/api/speaking/attempts/page') {
      return options?.params?.query?.cursor
        ? { data: { items: nextSpeakingEntries, next_cursor: null } }
        : { data: { items: speakingEntries, next_cursor: nextSpeakingCursor } }
    }
    if (path === '/api/writing/prompts/{prompt_id}/feedback') {
      return { data: { items: feedbacks, next_cursor: null } }
    }
    if (path === '/api/writing/history/page') {
      if (options?.params?.query?.cursor) {
        return { data: { items: nextWritingEntries, next_cursor: null } }
      }
      return {
        data: {
          items: [
            {
              prompt_id: 4,
              course_slug: 'voa-level-1',
              course_title: course.title,
              unit_slug: '45-49',
              lesson_number: 45,
              lesson_title: lesson.title,
              prompt_title: 'Compare caminhos',
              updated_at: '2026-10-08T00:30:00Z',
              revision_count: 1,
              feedback_count: feedbacks.length,
            },
          ],
          next_cursor: nextWritingCursor,
        },
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
  it('explica a regra antiga no histórico sem alterar o resultado salvo', async () => {
    const user = userEvent.setup()
    mockCurriculum()
    mockQueries([], [{
      id: 77, algorithm_version: 'legacy-v1', rubric_version: null,
      evaluation_scope: 'Não garante gramática correta.', created_at: '2026-10-08T00:30:00Z',
    }])
    renderNotebook()
    const summary = await screen.findByText('Regras das análises salvas')
    await user.click(summary)
    expect(summary.closest('details')).toHaveAttribute('open')
    expect(await screen.findByText('Regra anterior · resultado preservado')).toBeVisible()
    expect(screen.getByText(/O resultado original não foi recalculado/)).toBeVisible()
  })

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

    expect(clientMocks.GET).toHaveBeenCalledWith('/api/me/notebook/page', {
      params: {
        query: {
          lesson: undefined,
          kind: undefined,
          course: 'voa-level-1',
          unit: '45-49',
          limit: 20,
          cursor: undefined,
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

  it('carrega a próxima página sem substituir as anotações visíveis', async () => {
    const user = userEvent.setup()
    mockCurriculum()
    const older = {
      ...entry,
      id: 7,
      content: 'This older note remains in the same filtered history.',
      updated_at: '2026-10-07T00:30:00Z',
    }
    mockQueries([entry], [], 'cursor-page-2', [older])
    renderNotebook()

    expect(await screen.findByText(entry.content)).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Carregar mais anotações' }))

    expect(await screen.findByText(older.content)).toBeVisible()
    expect(screen.getByText(entry.content)).toBeVisible()
    expect(clientMocks.GET).toHaveBeenCalledWith('/api/me/notebook/page', {
      params: {
        query: {
          lesson: undefined,
          kind: undefined,
          course: 'voa-level-1',
          unit: '45-49',
          limit: 20,
          cursor: 'cursor-page-2',
        },
      },
    })
  })

  it('carrega mais textos sem misturar a página anterior e anuncia o novo total', async () => {
    const user = userEvent.setup()
    mockCurriculum()
    const olderWriting = {
      prompt_id: 3,
      course_slug: 'voa-level-1',
      course_title: course.title,
      unit_slug: '45-49',
      lesson_number: 45,
      lesson_title: lesson.title,
      prompt_title: 'Texto anterior',
      updated_at: '2026-10-07T00:30:00Z',
      revision_count: 2,
      feedback_count: 0,
    }
    mockQueries([], [], null, [], 'writing-page-2', [olderWriting])
    renderNotebook()

    expect(await screen.findByText('Compare caminhos')).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Carregar mais textos' }))

    expect(await screen.findByText('Texto anterior')).toBeVisible()
    expect(screen.getByText('Compare caminhos')).toBeVisible()
    await waitFor(() => expect(screen.getByText('2 textos carregados.')).toHaveFocus())
    expect(clientMocks.GET).toHaveBeenCalledWith('/api/writing/history/page', {
      params: {
        query: {
          course: 'voa-level-1',
          unit: '45-49',
          limit: 20,
          cursor: 'writing-page-2',
        },
      },
    })
  })

  it('carrega mais gravações sem perder a página anterior e preserva o foco', async () => {
    const user = userEvent.setup()
    mockCurriculum()
    const recording = {
      id: 41,
      course_slug: 'voa-level-1',
      course_title: course.title,
      unit_slug: '45-49',
      lesson_number: 45,
      cue_text: 'This land is your land.',
      duration_ms: 1900,
      created_at: '2026-10-15T12:00:00Z',
    }
    const olderRecording = {
      ...recording,
      id: 40,
      cue_text: 'This land is my land.',
      created_at: '2026-10-14T12:00:00Z',
    }
    mockQueries([], [], null, [], null, [], [recording], 'speaking-page-2', [olderRecording])
    clientMocks.DELETE.mockResolvedValue({ response: { ok: true } })
    renderNotebook()

    expect(await screen.findByText('This land is your land.')).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Carregar mais gravações' }))

    expect(await screen.findByText('This land is my land.')).toBeVisible()
    expect(screen.getByText('This land is your land.')).toBeVisible()
    await waitFor(() => expect(screen.getByText('2 gravações carregadas.')).toHaveFocus())
    expect(clientMocks.GET).toHaveBeenCalledWith('/api/speaking/attempts/page', {
      params: {
        query: {
          course: 'voa-level-1',
          unit: '45-49',
          limit: 20,
          cursor: 'speaking-page-2',
        },
      },
    })
    await user.click(screen.getAllByRole('button', { name: 'Excluir' })[1]!)
    expect(screen.queryByText('This land is my land.')).not.toBeInTheDocument()
    expect(screen.getByText('This land is your land.')).toBeVisible()
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
