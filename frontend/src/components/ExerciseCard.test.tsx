import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Exercise } from '../api/client'
import { listQueuedAttempts } from '../features/offline/attemptQueue'
import type { PracticeSessionItem } from '../features/practice/types'
import { ExerciseCard } from './ExerciseCard'

vi.mock('../api/client', async () => ({
  api: { GET: vi.fn(), POST: vi.fn() },
}))
const { api } = await import('../api/client')

const exercicio: Exercise = {
  id: 1,
  position: 0,
  activity_type: 'gap_fill',
  skill: 'grammar',
  objective: 'apply',
  options: null,
  prompt: 'A bicycle is `____` (fast) than a taxi.',
  hint: '1 palavra',
  hint_count: 2,
  explanation: '*fast* tem 1 sílaba → -er + than.',
}

function feedback(correct: boolean) {
  return {
    attempt_id: 10,
    correct,
    explanation: correct ? exercicio.explanation : null,
    feedback: {
      category: correct ? ('correct' as const) : ('extra_word' as const),
      message: correct
        ? 'A resposta corresponde a uma das formas aceitas.'
        : 'Há uma palavra ou estrutura a mais. Revise os trechos marcados.',
      tokens: correct
        ? [{ text: 'faster', status: 'keep' as const }]
        : [
            { text: 'more', status: 'review' as const },
            { text: 'fast', status: 'review' as const },
          ],
    },
  }
}

function montar(props: Partial<Parameters<typeof ExerciseCard>[0]> = {}) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ExerciseCard exercicio={exercicio} numero={1} userId={7} {...props} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  localStorage.clear()
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
})
afterEach(() => {
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
  vi.resetAllMocks()
})

describe('ExerciseCard', () => {
  it('mostra o enunciado com a dica, sem vazar a resposta', () => {
    montar()
    expect(screen.getByText(/A bicycle is/)).toBeInTheDocument()
    expect(screen.getByText(/1 palavra/)).toBeInTheDocument()
    expect(screen.queryByText(/faster/)).toBeNull()
  })

  it('o botão Verificar só liga quando há texto', async () => {
    const user = userEvent.setup()
    montar()
    const botao = screen.getByRole('button', { name: 'Verificar' })
    expect(botao).toBeDisabled()
    await user.type(screen.getByRole('textbox'), 'faster')
    expect(botao).toBeEnabled()
  })

  it('acerto: pede ao servidor e mostra a explicação', async () => {
    const user = userEvent.setup()
    vi.mocked(api.POST).mockResolvedValue({
      data: feedback(true),
      response: new Response(),
    } as never)

    const aoResponder = vi.fn()
    montar({ aoResponder })
    await user.type(screen.getByRole('textbox'), 'faster')
    await user.click(screen.getByRole('button', { name: 'Verificar' }))

    await waitFor(() => expect(screen.getByText('Correto')).toBeInTheDocument())
    expect(aoResponder).toHaveBeenCalledWith(true)
    // A correção é do servidor — o componente não compara nada sozinho.
    expect(api.POST).toHaveBeenCalledWith('/api/exercises/{exercise_id}/attempt', {
      params: { path: { exercise_id: 1 } },
      body: { answer: 'faster', idempotency_key: expect.any(String) },
    })
  })

  it('erro: sugere tentar de novo e não entrega o gabarito', async () => {
    const user = userEvent.setup()
    vi.mocked(api.POST).mockResolvedValue({
      data: feedback(false),
      response: new Response(),
    } as never)

    montar()
    await user.type(screen.getByRole('textbox'), 'more fast')
    await user.click(screen.getByRole('button', { name: 'Verificar' }))

    await waitFor(() => expect(screen.getByText('Ainda não')).toBeInTheDocument())
    expect(screen.getByText(/palavra ou estrutura a mais/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument()
    expect(screen.queryByText('faster')).toBeNull()
  })

  it('Resposta busca o gabarito num endpoint separado', async () => {
    const user = userEvent.setup()
    vi.mocked(api.GET).mockResolvedValue({
      data: { answers: ['should', 'ought to'], explanation: 'os dois valem.' },
      response: new Response(),
    } as never)

    montar()
    await user.click(screen.getByRole('button', { name: 'Resposta' }))

    await waitFor(() => expect(screen.getByText('should · ought to')).toBeInTheDocument())
    expect(api.GET).toHaveBeenCalledWith('/api/exercises/{exercise_id}/answer', {
      params: { path: { exercise_id: 1 } },
    })
  })

  it('API fora do ar preserva a tentativa para sincronizar depois', async () => {
    const user = userEvent.setup()
    vi.mocked(api.POST).mockResolvedValue({ data: undefined, response: undefined } as never)

    montar()
    await user.type(screen.getByRole('textbox'), 'faster')
    await user.click(screen.getByRole('button', { name: 'Verificar' }))

    await waitFor(() => expect(screen.getByText('Na fila')).toBeInTheDocument())
    expect(screen.getByText(/salva neste dispositivo/)).toBeInTheDocument()
  })

  it('enfileira imediatamente quando o navegador já está offline', async () => {
    const user = userEvent.setup()
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })

    montar({ practiceSessionId: 44, courseSlug: 'voa-level-1', lessonNumber: 31 })
    await user.type(screen.getByRole('textbox'), 'faster')
    await user.click(screen.getByRole('button', { name: 'Verificar' }))

    expect(await screen.findByText('Na fila')).toBeInTheDocument()
    expect(api.POST).not.toHaveBeenCalled()
    expect(listQueuedAttempts(7)).toEqual([
      expect.objectContaining({
        exerciseId: 1,
        answer: 'faster',
        sessionId: 44,
        courseSlug: 'voa-level-1',
        lessonNumber: 31,
      }),
    ])
  })

  it('enfileira com a mesma chave e o contexto se a conexão cai durante o POST', async () => {
    const user = userEvent.setup()
    vi.mocked(api.POST).mockRejectedValueOnce(new TypeError('Failed to fetch'))

    montar({ practiceSessionId: 44, courseSlug: 'voa-level-1', lessonNumber: 31 })
    await user.type(screen.getByRole('textbox'), 'faster')
    await user.click(screen.getByRole('button', { name: 'Verificar' }))

    await waitFor(() => expect(screen.getByText('Na fila')).toBeInTheDocument())
    const rawRequest = vi.mocked(api.POST).mock.calls[0]?.[1]
    if (!rawRequest) throw new Error('A tentativa não chegou à API.')
    const request = rawRequest as { body: { idempotency_key: string } }
    expect(listQueuedAttempts(7)).toEqual([
      expect.objectContaining({
        exerciseId: 1,
        answer: 'faster',
        idempotencyKey: request.body.idempotency_key,
        sessionId: 44,
        courseSlug: 'voa-level-1',
        lessonNumber: 31,
      }),
    ])
  })

  it('não enfileira uma resposta HTTP de erro', async () => {
    const user = userEvent.setup()
    vi.mocked(api.POST).mockResolvedValue({
      data: undefined,
      response: new Response(null, { status: 422 }),
    } as never)

    montar({ practiceSessionId: 44, courseSlug: 'voa-level-1', lessonNumber: 31 })
    await user.type(screen.getByRole('textbox'), 'faster')
    await user.click(screen.getByRole('button', { name: 'Verificar' }))

    expect(await screen.findByText('Erro')).toBeInTheDocument()
    expect(listQueuedAttempts(7)).toEqual([])
  })

  it('libera as dicas em níveis e exige tentativa antes da segunda', async () => {
    const user = userEvent.setup()
    vi.mocked(api.GET)
      .mockResolvedValueOnce({
        data: { level: 1, content: 'Pense no comparativo curto.' },
        response: new Response(),
      } as never)
      .mockResolvedValueOnce({
        data: { level: 2, content: 'Adicione a terminação *-er*.' },
        response: new Response(),
      } as never)
    vi.mocked(api.POST).mockResolvedValue({ data: feedback(false), response: new Response() } as never)

    montar()
    await user.click(screen.getByRole('button', { name: 'Dica 1' }))
    expect(await screen.findByText('Pense no comparativo curto.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Dica 2' })).toBeDisabled()

    await user.type(screen.getByRole('textbox'), 'more fast')
    await user.click(screen.getByRole('button', { name: 'Verificar' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Dica 2' })).toBeEnabled())
    await user.click(screen.getByRole('button', { name: 'Dica 2' }))

    expect(await screen.findByText(/Adicione a terminação/)).toBeInTheDocument()
    expect(api.GET).toHaveBeenLastCalledWith('/api/exercises/{exercise_id}/hints/{level}', {
      params: { path: { exercise_id: 1, level: 2 } },
    })
  })

  it('renderiza atividade de múltipla escolha sem campo de texto', async () => {
    const user = userEvent.setup()
    vi.mocked(api.POST).mockResolvedValue({ data: feedback(true), response: new Response() } as never)
    montar({
      exercicio: {
        ...exercicio,
        activity_type: 'multiple_choice',
        skill: 'listening',
        options: ['bus', 'taxi', 'Metro'],
      },
    })

    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    await user.click(screen.getByRole('radio', { name: 'Metro' }))
    await user.click(screen.getByRole('button', { name: 'Verificar' }))

    await waitFor(() => expect(screen.getByText('Correto')).toBeInTheDocument())
    expect(api.POST).toHaveBeenCalledWith('/api/exercises/{exercise_id}/attempt', {
      params: { path: { exercise_id: 1 } },
      body: { answer: 'Metro', idempotency_key: expect.any(String) },
    })
  })

  it('monta uma frase ordenando palavras pelo teclado ou clique', async () => {
    const user = userEvent.setup()
    vi.mocked(api.POST).mockResolvedValue({ data: feedback(true), response: new Response() } as never)
    montar({
      exercicio: {
        ...exercicio,
        activity_type: 'reorder',
        options: ['You', 'should', 'study'],
      },
    })

    for (const word of ['You', 'should', 'study']) {
      await user.click(screen.getByRole('button', { name: `Adicionar ${word}` }))
    }
    expect(screen.getByLabelText('Frase montada')).toHaveTextContent('Youshouldstudy')
    await user.click(screen.getByRole('button', { name: 'Verificar' }))

    await waitFor(() => expect(api.POST).toHaveBeenCalled())
    expect(api.POST).toHaveBeenCalledWith('/api/exercises/{exercise_id}/attempt', {
      params: { path: { exercise_id: 1 } },
      body: { answer: 'You should study', idempotency_key: expect.any(String) },
    })
  })

  it('usa endpoints da sessão e informa quando a resposta foi revelada', async () => {
    const user = userEvent.setup()
    vi.mocked(api.POST).mockResolvedValue({
      data: {
        answers: ['faster'],
        explanation: 'Use **-er** com adjetivos curtos.',
        item: {},
      },
      response: new Response(),
    } as never)
    const onActivity = vi.fn()

    montar({ practiceSessionId: 44, onActivity })
    await user.click(screen.getByRole('button', { name: 'Resposta' }))

    expect(await screen.findByText('faster')).toBeInTheDocument()
    expect(api.POST).toHaveBeenCalledWith(
      '/api/practice-sessions/{session_id}/items/{exercise_id}/reveal',
      { params: { path: { session_id: 44, exercise_id: 1 } } },
    )
    expect(onActivity).toHaveBeenCalledWith({ type: 'reveal', exerciseId: 1 })
  })

  it('restaura um item concluído sem permitir uma tentativa duplicada', () => {
    const initialSessionItem: PracticeSessionItem = {
      position: 0,
      exercise: exercicio,
      attempt_count: 2,
      first_try_correct: false,
      highest_hint_level: 1,
      opened_hints: [{ level: 1, content: 'Pense no comparativo curto.' }],
      answer_revealed: false,
      completed_at: '2026-10-08T12:00:00Z',
      outcome: 'corrected',
      last_feedback: null,
      answers: null,
      explanation: 'Use **faster than**.',
    }

    montar({ practiceSessionId: 44, initialSessionItem })

    expect(screen.getByText('Correto')).toBeInTheDocument()
    expect(screen.getByText('Pense no comparativo curto.')).toBeInTheDocument()
    expect(screen.getByRole('textbox')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Verificar' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Resposta' })).toBeDisabled()
  })

  it('devolve o foco à primeira opção ao tentar novamente', async () => {
    const user = userEvent.setup()
    vi.mocked(api.POST).mockResolvedValue({ data: feedback(false), response: new Response() } as never)
    montar({
      exercicio: {
        ...exercicio,
        activity_type: 'multiple_choice',
        options: ['faster', 'more fast'],
      },
    })

    await user.click(screen.getByRole('radio', { name: 'more fast' }))
    await user.click(screen.getByRole('button', { name: 'Verificar' }))
    await user.click(await screen.findByRole('button', { name: 'Tentar novamente' }))

    expect(screen.getByRole('radio', { name: 'faster' })).toHaveFocus()
  })
})
