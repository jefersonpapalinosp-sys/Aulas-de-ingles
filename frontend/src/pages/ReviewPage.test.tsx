import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ReviewPage } from './ReviewPage'

const avaliar = vi.fn()
const setStatus = vi.fn()
const deleteItem = vi.fn()
const useDueCards = vi.fn()
const useSuspended = vi.fn()

vi.mock('../api/review', () => ({
  useDueCards: (filters: unknown) => useDueCards(filters),
  useAvaliar: () => ({ mutate: avaliar, isPending: false }),
  useSuspendedReviewItems: () => useSuspended(),
  useSetReviewItemStatus: () => ({ mutate: setStatus, isPending: false }),
  useDeleteReviewItem: () => ({ mutate: deleteItem, isPending: false }),
}))

const carta = {
  id: 7,
  item_type: 'vocabulary',
  skill: 'vocabulary',
  prompt: 'sold out',
  prompt_note: '/soʊld aʊt/',
  answer: 'esgotado',
  context: 'The tickets are sold out.',
  reason: 'Vocabulário incluído no deck. É a primeira revisão deste item.',
  estimated_seconds: 45,
  media_url: null,
  cue_start_seconds: null,
  cue_end_seconds: null,
  status: 'active',
  vocab_item_id: 70,
  lesson_number: 31,
  ease_factor: 2.5,
  interval_days: 0,
  repetitions: 0,
  lapses: 0,
  due_at: '2026-10-07T12:00:00Z',
}

function montar() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ReviewPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => vi.resetAllMocks())

beforeEach(() => {
  useSuspended.mockReturnValue({ data: [], isPending: false, error: null })
})

describe('ReviewPage', () => {
  it('a frente da carta não entrega a tradução', () => {
    useDueCards.mockReturnValue({ data: [carta], isPending: false, error: null })
    montar()
    expect(screen.getByText('sold out')).toBeInTheDocument()
    expect(screen.getByText('/soʊld aʊt/')).toBeInTheDocument()
    expect(screen.queryByText('esgotado')).toBeNull()
  })

  it('virar mostra tradução, exemplo e as quatro notas', async () => {
    const user = userEvent.setup()
    useDueCards.mockReturnValue({ data: [carta], isPending: false, error: null })
    montar()

    await user.click(screen.getByRole('button', { name: 'Mostrar resposta' }))
    expect(screen.getByText('esgotado')).toBeInTheDocument()
    expect(screen.getByText(/The tickets are sold out/)).toBeInTheDocument()
    for (const rotulo of ['Errei', 'Difícil', 'Bom', 'Fácil']) {
      expect(screen.getByText(rotulo)).toBeInTheDocument()
    }
  })

  it('explica por que o item voltou e permite suspendê-lo', async () => {
    const user = userEvent.setup()
    useDueCards.mockReturnValue({ data: [carta], isPending: false, error: null })
    montar()

    expect(screen.getByText('Por que voltou?')).toBeInTheDocument()
    expect(screen.getByText(/primeira revisão/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Suspender item' }))
    expect(setStatus).toHaveBeenCalledWith(
      { itemId: 7, status: 'suspended' },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    )
  })

  it('filtra por tipo, competência e duração', async () => {
    const user = userEvent.setup()
    useDueCards.mockReturnValue({ data: [carta], isPending: false, error: null })
    montar()

    await user.selectOptions(screen.getByLabelText('Tipo'), 'grammar_error')
    await user.selectOptions(screen.getByLabelText('Competência'), 'grammar')
    await user.selectOptions(screen.getByLabelText('Duração'), '2')

    expect(useDueCards).toHaveBeenLastCalledWith({
      itemType: 'grammar_error',
      skill: 'grammar',
      maxMinutes: 2,
    })
  })

  it('reativa um item suspenso', async () => {
    const user = userEvent.setup()
    useDueCards.mockReturnValue({ data: [], isPending: false, error: null })
    useSuspended.mockReturnValue({
      data: [{ ...carta, status: 'suspended' }],
      isPending: false,
      error: null,
    })
    montar()

    await user.click(screen.getByRole('button', { name: 'Reativar' }))
    expect(setStatus).toHaveBeenCalledWith({ itemId: 7, status: 'active' })
  })

  it('o teclado vira a carta e avalia', async () => {
    const user = userEvent.setup()
    useDueCards.mockReturnValue({ data: [carta], isPending: false, error: null })
    montar()

    await user.keyboard(' ')
    expect(screen.getByText('esgotado')).toBeInTheDocument()

    await user.keyboard('3')
    await waitFor(() =>
      expect(avaliar).toHaveBeenCalledWith(
        { cardId: 7, quality: 4 },
        expect.objectContaining({ onSuccess: expect.any(Function) }),
      ),
    )
  })

  it('"Errei" manda qualidade abaixo do corte de acerto', async () => {
    const user = userEvent.setup()
    useDueCards.mockReturnValue({ data: [carta], isPending: false, error: null })
    montar()

    await user.click(screen.getByRole('button', { name: 'Mostrar resposta' }))
    await user.click(screen.getByText('Errei'))

    expect(avaliar.mock.calls[0]![0]).toEqual({ cardId: 7, quality: 1 })
  })

  it('deck vazio explica como encher', () => {
    useDueCards.mockReturnValue({ data: [], isPending: false, error: null })
    montar()
    expect(screen.getByText('Nada para revisar agora')).toBeInTheDocument()
    expect(screen.getByText(/Marque uma aula como estudada/)).toBeInTheDocument()
  })

  it('erro de rede vira mensagem com botão de repetir', () => {
    useDueCards.mockReturnValue({
      data: undefined,
      isPending: false,
      error: new Error('Não foi possível falar com a API.'),
      refetch: vi.fn(),
    })
    montar()
    expect(screen.getByRole('alert')).toHaveTextContent('Não foi possível falar com a API.')
    expect(screen.getByRole('button', { name: 'Tentar de novo' })).toBeInTheDocument()
  })
})
