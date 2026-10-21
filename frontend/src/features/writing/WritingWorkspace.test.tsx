import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { WritingPrompt } from '../../api/client'
import { WritingWorkspace } from './WritingWorkspace'

const apiMocks = vi.hoisted(() => ({
  GET: vi.fn(),
  PUT: vi.fn(),
  POST: vi.fn(),
}))

vi.mock('../../api/client', () => ({ api: apiMocks }))

const prompt: WritingPrompt = {
  id: 4,
  position: 0,
  title: 'Compare caminhos para o estádio',
  instructions: 'Write four sentences comparing two ways to travel.',
  min_words: 35,
  min_sentences: 4,
  requirements: [
    { label: 'um comparativo com than', terms: ['than'], kind: 'markers', match_mode: 'any', count_mode: 'occurrences', min_count: 1 },
    { label: 'um conselho com should ou ought to', terms: ['should', 'ought to'], kind: 'markers', match_mode: 'any', count_mode: 'occurrences', min_count: 1 },
  ],
}

function renderWorkspace() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = render(
    <QueryClientProvider client={queryClient}>
      <WritingWorkspace prompt={prompt} userId={7} />
    </QueryClientProvider>,
  )
  return { ...view, queryClient }
}

function mockDraft(
  draft: Record<string, unknown>,
  versions: Record<string, unknown>[] = [],
) {
  apiMocks.GET.mockImplementation(async (path) =>
    path === '/api/writing/prompts/{prompt_id}/versions'
      ? { data: { items: versions, next_cursor: null } }
      : { data: draft },
  )
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.clearAllMocks()
  window.localStorage.clear()
})

describe('WritingWorkspace', () => {
  it('reutiliza chave após perda de resposta e mantém texto diante de análise já iniciada', async () => {
    apiMocks.GET.mockImplementation(async (path) => ({ data: path.includes('assist/status')
      ? { writing_enabled: true, remaining_today: 2, reserved_today: 0, consumed_today: 1, cost_microusd_today: 0 }
      : path === '/api/writing/prompts/{prompt_id}/versions'
        ? { items: [], next_cursor: null }
        : { prompt_id: 4, revision: 0, text: 'Keep this draft.' } }))
    apiMocks.POST.mockRejectedValueOnce(new TypeError('network'))
      .mockResolvedValue({ response: new Response(null, { status: 409 }) })
    renderWorkspace()
    const editor = screen.getByRole('textbox', { name: 'Seu texto em inglês' })
    await waitFor(() => expect(editor).toHaveValue('Keep this draft.'))
    await userEvent.click(await screen.findByRole('checkbox'))
    const analyze = screen.getByRole('button', { name: 'Analisar texto' })
    await userEvent.click(analyze)
    expect(await screen.findByText(/Análise indisponível/)).toBeInTheDocument()
    await userEvent.click(analyze)
    expect(await screen.findByText(/Análise já iniciada/)).toBeInTheDocument()
    const first = apiMocks.POST.mock.calls[0]![1].body
    expect(first.assisted).toBe(true)
    expect(first.operation_key).toMatch(/^[a-f0-9-]{36}$/)
    expect(apiMocks.POST.mock.calls[1]![1].body.operation_key).toBe(first.operation_key)
    expect(editor).toHaveValue('Keep this draft.')
    fireEvent.change(editor, { target: { value: 'Changed text.' } })
    await userEvent.click(analyze)
    expect(apiMocks.POST.mock.calls[2]![1].body.operation_key).not.toBe(first.operation_key)
  })

  it('não aplica análise atrasada do texto A ao texto B', async () => {
    mockDraft({ prompt_id: 4, revision: 0, text: 'Text A.' })
    let resolve!: (value: unknown) => void
    apiMocks.POST.mockReturnValue(new Promise((done) => { resolve = done }))
    renderWorkspace()
    const editor = screen.getByRole('textbox', { name: 'Seu texto em inglês' })
    await waitFor(() => expect(editor).toHaveValue('Text A.'))
    await userEvent.click(screen.getByRole('button', { name: 'Analisar texto' }))
    fireEvent.change(editor, { target: { value: 'Text B.' } })
    await act(async () => resolve({ data: { id: 1, ready: true, checks: [] } }))
    expect(screen.queryByRole('heading', { name: 'Critérios automáticos atendidos' })).not.toBeInTheDocument()
    expect(editor).toHaveValue('Text B.')
  })

  it('preserva os dois textos no conflito e só sobrescreve após escolha explícita', async () => {
    const remote = { prompt_id: 4, revision: 2, text: 'Other device.', updated_at: '2026-10-14T03:00:00Z', revisions: [] }
    mockDraft({ ...remote, revision: 1, text: 'Original.' })
    apiMocks.PUT.mockResolvedValueOnce({ response: new Response(null, { status: 409 }), error: { detail: { current: remote } } })
      .mockResolvedValue({ data: { ...remote, revision: 3, text: 'My draft.' } })
    renderWorkspace()
    const editor = screen.getByRole('textbox', { name: 'Seu texto em inglês' })
    await waitFor(() => expect(editor).toHaveValue('Original.'))
    fireEvent.change(editor, { target: { value: 'My draft.' } })
    expect(await screen.findByRole('heading', { name: 'Há duas versões do rascunho' }, { timeout: 1800 })).toBeInTheDocument()
    expect(editor).toHaveValue('My draft.')
    expect(screen.getByRole('textbox', { name: 'Texto salvo na conta' })).toHaveValue('Other device.')
    expect(apiMocks.PUT).toHaveBeenCalledTimes(1)
    expect(apiMocks.PUT.mock.calls[0]![1].body.expected_revision).toBe(1)
    await userEvent.click(screen.getByRole('button', { name: 'Preparar cópia dos dois' }))
    expect(screen.getByRole('textbox', { name: 'Selecione e copie os dois textos' })).toHaveValue('Neste dispositivo:\nMy draft.\n\nNa conta:\nOther device.')
    await userEvent.click(screen.getByRole('button', { name: 'Manter meu texto' }))
    await waitFor(() => expect(apiMocks.PUT).toHaveBeenCalledTimes(2))
    expect(apiMocks.PUT.mock.calls[1]![1].body).toEqual({ text: 'My draft.', expected_revision: 2 })
    expect(await screen.findByText('Rascunho salvo.')).toBeInTheDocument()
  })

  it('backup sem revisão não sobrescreve automaticamente a conta', async () => {
    localStorage.setItem('aulas-ingles:writing-draft:v1:7:4', 'Recovered local.')
    mockDraft({ prompt_id: 4, revision: 8, text: 'Account text.', updated_at: null })
    renderWorkspace()
    expect(await screen.findByRole('heading', { name: 'Há duas versões do rascunho' })).toBeInTheDocument()
    expect(screen.getByText(/Rascunho recuperado neste dispositivo/)).toBeInTheDocument()
    expect(apiMocks.PUT).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Usar texto da conta' }))
    expect(screen.getByRole('textbox', { name: 'Seu texto em inglês' })).toHaveValue('Account text.')
    expect(apiMocks.PUT).not.toHaveBeenCalled()
  })

  it('resposta de autosave desmontado não apaga backup novo', async () => {
    mockDraft({ prompt_id: 4, revision: 0, text: '' })
    let resolve!: (value: unknown) => void
    apiMocks.PUT.mockReturnValue(new Promise((done) => { resolve = done }))
    const view = renderWorkspace()
    const editor = screen.getByRole('textbox', { name: 'Seu texto em inglês' })
    await waitFor(() => expect(editor).toBeEnabled())
    fireEvent.change(editor, { target: { value: 'Pending old.' } })
    await waitFor(() => expect(apiMocks.PUT).toHaveBeenCalled(), { timeout: 1800 })
    view.unmount()
    localStorage.setItem('aulas-ingles:writing-draft:v1:7:4', 'Newer local.')
    await act(async () => resolve({ data: { prompt_id: 4, revision: 1, text: 'Pending old.', revisions: [] } }))
    expect(localStorage.getItem('aulas-ingles:writing-draft:v1:7:4')).toBe('Newer local.')
  })
  it('quota e falha remota mantêm texto editável, sem afirmar persistência', async () => {
    mockDraft({ prompt_id: 4, text: '' })
    apiMocks.PUT.mockRejectedValue(new TypeError('offline'))
    apiMocks.POST.mockRejectedValue(new TypeError('offline'))
    renderWorkspace()
    const editor = screen.getByRole('textbox', { name: 'Seu texto em inglês' })
    await waitFor(() => expect(editor).toBeEnabled())
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('', 'QuotaExceededError') })
    fireEvent.change(editor, { target: { value: 'Keep this draft.' } })
    expect(editor).toHaveValue('Keep this draft.')
    expect(screen.getByRole('alert')).toHaveTextContent('cheio')
    await waitFor(() => expect(apiMocks.PUT).toHaveBeenCalled(), { timeout: 1800 })
    expect(await screen.findByText(/Texto apenas nesta tela/)).toBeInTheDocument()
    expect(screen.queryByText('Salvo neste dispositivo; sincronização pendente.')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Analisar texto' }))
    expect(await screen.findByText(/confira o estado de salvamento/)).toBeInTheDocument()
    expect(editor).toBeEnabled()
  })

  it('leitura bloqueada não desmonta editor nem afirma que recuperou backup', async () => {
    mockDraft({ prompt_id: 4, text: 'Remote draft.' })
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new DOMException('', 'SecurityError') })
    renderWorkspace()
    await waitFor(() => expect(screen.getByRole('textbox')).toHaveValue('Remote draft.'))
    expect(screen.getByRole('alert')).toHaveTextContent('rascunho local mais recente')
    expect(screen.getByRole('textbox')).toBeEnabled()
  })

  it('falha em remover backup não transforma sucesso remoto em falha de salvamento', async () => {
    mockDraft({ prompt_id: 4, text: '' })
    apiMocks.PUT.mockResolvedValue({ data: { prompt_id: 4, text: 'Saved.', revisions: [] } })
    renderWorkspace()
    const editor = screen.getByRole('textbox')
    await waitFor(() => expect(editor).toBeEnabled())
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => { throw new DOMException('', 'SecurityError') })
    fireEvent.change(editor, { target: { value: 'Saved.' } })
    expect(await screen.findByText('Rascunho salvo.', {}, { timeout: 1800 })).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Não foi possível remover a cópia local')
    expect(localStorage.getItem('aulas-ingles:writing-draft:v1:7:4')).toBe('Saved.')
  })

  it('recupera e salva o rascunho automaticamente', async () => {
    const user = userEvent.setup()
    mockDraft({ prompt_id: 4, text: 'Old text.', updated_at: null })
    apiMocks.PUT.mockImplementation(async (_path, options) => ({
      data: {
        prompt_id: 4,
        text: options.body.text,
        updated_at: '2026-10-07T22:30:00Z',
        revisions: [],
      },
    }))

    renderWorkspace()
    const editor = await screen.findByRole('textbox', { name: 'Seu texto em inglês' })
    await waitFor(() => expect(editor).toHaveValue('Old text.'))

    await user.clear(editor)
    await user.type(editor, 'The train is faster than the bus.')

    expect(window.localStorage.getItem('aulas-ingles:writing-draft:v1:7:4')).toBe(
      'The train is faster than the bus.',
    )
    await waitFor(() => expect(apiMocks.PUT).toHaveBeenCalled(), { timeout: 1800 })
    expect(await screen.findByText('Rascunho salvo.')).toBeInTheDocument()
    expect(window.localStorage.getItem('aulas-ingles:writing-draft:v1:7:4')).toBeNull()
  })

  it('mostra critérios de correção e cria uma versão restaurável', async () => {
    const user = userEvent.setup()
    mockDraft({ prompt_id: 4, text: '', updated_at: null })
    apiMocks.PUT.mockResolvedValue({
      data: { prompt_id: 4, text: '', updated_at: '2026-10-07T22:30:00Z', revisions: [] },
    })
    apiMocks.POST.mockImplementation(async (path) => {
      if (path.endsWith('/feedback')) {
        return {
          data: {
            word_count: 39,
            sentence_count: 4,
            ready: true,
            algorithm_version: 'writing-rules-v2',
            rubric_version: `sha256:${'a'.repeat(64)}`,
            evaluation_scope: 'Não garante gramática correta.',
            checks: [
              {
                code: 'word_count',
                label: 'Pelo menos 35 palavras',
                passed: true,
                suggestion: 'Acrescente detalhes.',
              },
            ],
          },
        }
      }
      return {
        data: {
          id: 12,
          version: 1,
          text: 'The train is faster than the bus.',
          created_at: '2026-10-07T22:30:00Z',
        },
      }
    })

    const { queryClient } = renderWorkspace()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    const editor = await screen.findByRole('textbox', { name: 'Seu texto em inglês' })
    await waitFor(() => expect(editor).toBeEnabled())
    await user.type(editor, 'The train is faster than the bus.')
    await user.click(screen.getByRole('button', { name: 'Analisar texto' }))

    expect(
      await screen.findByRole('heading', { name: 'Critérios automáticos atendidos' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Pelo menos 35 palavras')).toBeInTheDocument()
    expect(screen.getByText(/Regra writing-rules-v2/)).toBeInTheDocument()
    expect(screen.getByText('Não garante gramática correta.')).toBeInTheDocument()
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['course-completion'] })

    await user.click(screen.getByRole('button', { name: 'Criar versão' }))
    expect(await screen.findByText('Versão 1 criada.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Versões salvas' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Restaurar no editor' })).toBeInTheDocument()
  })

  it('compara uma versão salva com o texto atual palavra por palavra', async () => {
    const user = userEvent.setup()
    mockDraft(
      {
        prompt_id: 4,
        text: 'The train is faster than the bus.',
        updated_at: '2026-10-08T00:30:00Z',
      },
      [
        {
          id: 10,
          version: 1,
          text: 'The bus is fast.',
          created_at: '2026-10-07T22:30:00Z',
        },
      ],
    )

    const { container } = renderWorkspace()
    await user.click(await screen.findByRole('button', { name: 'Comparar com texto atual' }))

    expect(screen.getByRole('heading', { name: 'Versão 1 → texto atual' })).toBeInTheDocument()
    expect(container.querySelector('.writing-diff-copy del')).toHaveTextContent('bus')
    expect(container.querySelector('.writing-diff-copy ins')).toHaveTextContent('train')
    await user.click(screen.getByRole('button', { name: 'Fechar comparação' }))
    expect(screen.queryByRole('heading', { name: 'Versão 1 → texto atual' })).not.toBeInTheDocument()
  })

  it('carrega mais versões e move o foco para o resultado anunciado', async () => {
    const user = userEvent.setup()
    apiMocks.GET.mockImplementation(async (path, options) => {
      if (path !== '/api/writing/prompts/{prompt_id}/versions') {
        return { data: { prompt_id: 4, revision: 2, text: 'Current text.' } }
      }
      return options?.params?.query?.cursor
        ? {
            data: {
              items: [{ id: 10, version: 1, text: 'First.', created_at: '2026-10-14T12:00:00Z' }],
              next_cursor: null,
            },
          }
        : {
            data: {
              items: [{ id: 11, version: 2, text: 'Second.', created_at: '2026-10-15T12:00:00Z' }],
              next_cursor: 'versions-page-2',
            },
          }
    })
    apiMocks.POST.mockResolvedValue({
      data: {
        id: 12,
        version: 3,
        draft_revision: 2,
        text: 'Current text.',
        created_at: '2026-10-15T13:00:00Z',
      },
    })
    renderWorkspace()

    expect(await screen.findByText('Versão 2')).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Carregar mais versões' }))

    expect(await screen.findByText('Versão 1')).toBeVisible()
    expect(screen.getByText('Versão 2')).toBeVisible()
    await waitFor(() => expect(screen.getByText('2 versões carregadas.')).toHaveFocus())
    expect(apiMocks.GET).toHaveBeenCalledWith('/api/writing/prompts/{prompt_id}/versions', {
      params: {
        path: { prompt_id: 4 },
        query: { limit: 20, cursor: 'versions-page-2' },
      },
    })
    await user.click(screen.getByRole('button', { name: 'Criar versão' }))
    expect(await screen.findByText('Versão 3')).toBeVisible()
    expect(screen.getByText('Versão 2')).toBeVisible()
    expect(screen.getByText('Versão 1')).toBeVisible()
  })

  it('faz opt-in explícito, mostra baixa confiança e permite avaliar a assistência', async () => {
    const user = userEvent.setup()
    apiMocks.GET.mockImplementation(async (path) =>
      path === '/api/assist/status'
        ? {
            data: {
              transcription_enabled: false,
              writing_enabled: true,
              evaluation_only: true,
              daily_quota: 5,
              used_today: 0,
              remaining_today: 5,
              retention_days: 30,
              cost_microusd_today: 0,
            },
          }
        : path === '/api/writing/prompts/{prompt_id}/versions'
          ? { data: { items: [], next_cursor: null } }
          : { data: { prompt_id: 4, text: '', updated_at: null } },
    )
    const assistedFeedback = {
      id: 81,
      word_count: 5,
      sentence_count: 1,
      ready: false,
      checks: [],
      analysis_mode: 'assisted',
      automated: true,
      evaluation_only: true,
      provider: 'provider-test',
      assisted_summary: 'Revise a clareza da comparação.',
      assisted_suggestions: [{ criterion: 'clarity', message: 'Explique sua escolha.' }],
      assisted_confidence: 0.61,
      low_confidence: true,
      assisted_cost_microusd: 800,
      assisted_error_code: null,
      human_rating: null,
      created_at: '2026-10-07T23:50:00Z',
    }
    apiMocks.POST.mockResolvedValue({ data: assistedFeedback })
    apiMocks.PUT.mockImplementation(async (path) =>
      path.includes('/rating')
        ? { data: { ...assistedFeedback, human_rating: 'helpful' } }
        : { data: { prompt_id: 4, text: 'The train is faster.', updated_at: null, revisions: [] } },
    )
    renderWorkspace()
    const editor = await screen.findByRole('textbox', { name: 'Seu texto em inglês' })
    await waitFor(() => expect(editor).toBeEnabled())
    await user.type(editor, 'The train is faster.')
    await user.click(await screen.findByRole('checkbox', { name: /Experimentar feedback/ }))
    await user.click(screen.getByRole('button', { name: 'Analisar texto' }))

    expect(await screen.findByText(/Automatizado por provider-test/)).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Baixa confiança')
    expect(apiMocks.POST).toHaveBeenCalledWith('/api/writing/prompts/{prompt_id}/feedback', {
      params: { path: { prompt_id: 4 } },
      body: { text: 'The train is faster.', assisted: true, operation_key: expect.any(String), expected_revision: 0 },
    })
    await user.click(screen.getByRole('button', { name: 'Sim' }))
    expect(apiMocks.PUT).toHaveBeenCalledWith('/api/writing/feedback/{feedback_id}/rating', {
      params: { path: { feedback_id: 81 } },
      body: { rating: 'helpful' },
    })
  })
})
