import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
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
    { label: 'um comparativo com than', terms: ['than'] },
    { label: 'um conselho com should ou ought to', terms: ['should', 'ought'] },
  ],
}

function renderWorkspace() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <WritingWorkspace prompt={prompt} userId={7} />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
})

describe('WritingWorkspace', () => {
  it('recupera e salva o rascunho automaticamente', async () => {
    const user = userEvent.setup()
    apiMocks.GET.mockResolvedValue({
      data: { prompt_id: 4, text: 'Old text.', updated_at: null, revisions: [] },
    })
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
    apiMocks.GET.mockResolvedValue({
      data: { prompt_id: 4, text: '', updated_at: null, revisions: [] },
    })
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

    renderWorkspace()
    const editor = await screen.findByRole('textbox', { name: 'Seu texto em inglês' })
    await waitFor(() => expect(editor).toBeEnabled())
    await user.type(editor, 'The train is faster than the bus.')
    await user.click(screen.getByRole('button', { name: 'Analisar texto' }))

    expect(
      await screen.findByRole('heading', { name: 'Texto pronto para uma nova versão' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Pelo menos 35 palavras')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Criar versão' }))
    expect(await screen.findByText('Versão 1 criada.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Versões salvas' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Restaurar no editor' })).toBeInTheDocument()
  })

  it('compara uma versão salva com o texto atual palavra por palavra', async () => {
    const user = userEvent.setup()
    apiMocks.GET.mockResolvedValue({
      data: {
        prompt_id: 4,
        text: 'The train is faster than the bus.',
        updated_at: '2026-10-08T00:30:00Z',
        revisions: [
          {
            id: 10,
            version: 1,
            text: 'The bus is fast.',
            created_at: '2026-10-07T22:30:00Z',
          },
        ],
      },
    })

    const { container } = renderWorkspace()
    await user.click(await screen.findByRole('button', { name: 'Comparar com texto atual' }))

    expect(screen.getByRole('heading', { name: 'Versão 1 → texto atual' })).toBeInTheDocument()
    expect(container.querySelector('.writing-diff-copy del')).toHaveTextContent('bus')
    expect(container.querySelector('.writing-diff-copy ins')).toHaveTextContent('train')
    await user.click(screen.getByRole('button', { name: 'Fechar comparação' }))
    expect(screen.queryByRole('heading', { name: 'Versão 1 → texto atual' })).not.toBeInTheDocument()
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
        : { data: { prompt_id: 4, text: '', updated_at: null, revisions: [] } },
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
      body: { text: 'The train is faster.', assisted: true },
    })
    await user.click(screen.getByRole('button', { name: 'Sim' }))
    expect(apiMocks.PUT).toHaveBeenCalledWith('/api/writing/feedback/{feedback_id}/rating', {
      params: { path: { feedback_id: 81 } },
      body: { rating: 'helpful' },
    })
  })
})
