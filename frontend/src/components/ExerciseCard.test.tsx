import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Exercise } from '../api/client'
import { ExerciseCard } from './ExerciseCard'

vi.mock('../api/client', async () => ({
  api: { GET: vi.fn(), POST: vi.fn() },
}))
const { api } = await import('../api/client')

const exercicio: Exercise = {
  id: 1,
  position: 0,
  prompt: 'A bicycle is `____` (fast) than a taxi.',
  hint: '1 palavra',
  explanation: '*fast* tem 1 sílaba → -er + than.',
}

function montar(props: Partial<Parameters<typeof ExerciseCard>[0]> = {}) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ExerciseCard exercicio={exercicio} numero={1} {...props} />
    </QueryClientProvider>,
  )
}

afterEach(() => vi.resetAllMocks())

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
      data: { correct: true, explanation: exercicio.explanation },
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
      body: { answer: 'faster' },
    })
  })

  it('erro: sugere tentar de novo e não entrega o gabarito', async () => {
    const user = userEvent.setup()
    vi.mocked(api.POST).mockResolvedValue({
      data: { correct: false, explanation: exercicio.explanation },
      response: new Response(),
    } as never)

    montar()
    await user.type(screen.getByRole('textbox'), 'more fast')
    await user.click(screen.getByRole('button', { name: 'Verificar' }))

    await waitFor(() => expect(screen.getByText('Ainda não')).toBeInTheDocument())
    expect(screen.getByText(/Tente de novo/)).toBeInTheDocument()
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

  it('API fora do ar vira mensagem, não tela travada', async () => {
    const user = userEvent.setup()
    vi.mocked(api.POST).mockResolvedValue({ data: undefined, response: undefined } as never)

    montar()
    await user.type(screen.getByRole('textbox'), 'faster')
    await user.click(screen.getByRole('button', { name: 'Verificar' }))

    await waitFor(() => expect(screen.getByText('Erro')).toBeInTheDocument())
  })
})
