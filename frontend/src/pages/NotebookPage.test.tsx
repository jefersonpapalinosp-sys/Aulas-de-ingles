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
  number: 31,
  title: 'Take Me Out to the Ball Game',
  title_pt: 'Leve-me ao jogo',
  grammar_tag: 'Comparatives',
  focus_points: ['comparatives'],
  story_note: null,
}

const entry = {
  id: 8,
  lesson_number: 31,
  lesson_title: lesson.title,
  kind: 'favorite_phrase' as const,
  content: 'A taxi is faster than a bus.',
  created_at: '2026-10-08T00:30:00Z',
  updated_at: '2026-10-08T00:30:00Z',
}

function mockQueries(entries = [entry]) {
  clientMocks.GET.mockImplementation(async (path) => {
    if (path === '/api/lessons') return { data: [lesson] }
    if (path === '/api/me/notebook') return { data: entries }
    if (path === '/api/speaking/attempts') return { data: [] }
    if (path === '/api/writing/history') {
      return {
        data: [
          {
            prompt_id: 4,
            lesson_number: 31,
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

function renderNotebook() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
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

describe('NotebookPage', () => {
  it('cria, edita e exclui uma anotação privada', async () => {
    const user = userEvent.setup()
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
      body: { lesson_number: 31, kind: 'note', content: 'New note' },
    })

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
