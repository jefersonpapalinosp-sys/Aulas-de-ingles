import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ReviewPage } from './ReviewPage'

const avaliar = vi.fn<(command: unknown, callbacks: { onError: (error: Error) => void }) => void>()
const setStatus = vi.fn<(command: unknown, callbacks: { onSuccess: () => void }) => void>()
const deleteItem = vi.fn()
const useDueCards = vi.fn<(filters: unknown) => unknown>()
const useSuspended = vi.fn<(filters: unknown, cursor: unknown) => unknown>()
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

vi.mock('../api/review', () => ({
  useDueCards: (filters: unknown) => useDueCards(filters),
  useAvaliar: () => ({ mutate: avaliar, isPending: false }),
  useSuspendedReviewItems: (filters: unknown, cursor: unknown) => useSuspended(filters, cursor),
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
  course_slug: 'voa-level-1',
  course_title: "Let's Learn English — Level 1",
  unit_slug: '45-49',
  lesson_number: 31,
  lesson_title: 'Take Me Out to the Ball Game',
  ease_factor: 2.5,
  interval_days: 0,
  repetitions: 0,
  lapses: 0,
  due_at: '2026-10-07T12:00:00Z',
}

function montar(route = '/revisar?course=voa-level-1&unit=45-49') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>
        <ReviewPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => vi.resetAllMocks())

beforeEach(() => {
  useSuspended.mockReturnValue({
    data: { items: [], next_cursor: null },
    isPending: false,
    isFetching: false,
    error: null,
  })
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
          published_lessons: 5,
          lessons: [],
          review: null,
        },
      ],
    },
    isPending: false,
    error: null,
  })
})

describe('ReviewPage', () => {
  it('ignora repetição de tecla/clique e reenvia exatamente a mesma avaliação', async () => {
    useDueCards.mockReturnValue({ data: [carta], isPending: false, error: null })
    montar()
    fireEvent.keyDown(window, { key: 'Enter' })
    fireEvent.keyDown(window, { key: '3', repeat: true })
    expect(avaliar).not.toHaveBeenCalled()
    fireEvent.keyDown(window, { key: '3' })
    fireEvent.keyDown(window, { key: '3' })
    expect(avaliar).toHaveBeenCalledTimes(1)
    const [command, callbacks] = avaliar.mock.calls[0]!
    act(() => callbacks.onError(new Error('response lost')))
    expect(screen.getByText(/Sua resposta foi preservada/)).toBeInTheDocument()
    expect(screen.getByText('sold out')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Reenviar a mesma avaliação' }))
    expect(avaliar).toHaveBeenCalledTimes(2)
    expect(avaliar.mock.calls[1]![0]).toEqual(command)
  })

  it('mantém a carta durante refetch enquanto a confirmação não chegou', () => {
    useDueCards.mockReturnValue({ data: [carta], isPending: false, error: null })
    montar()
    fireEvent.keyDown(window, { key: 'Enter' })
    fireEvent.keyDown(window, { key: '3' })
    useDueCards.mockReturnValue({ data: [], isPending: false, error: null })
    act(() => avaliar.mock.calls[0]![1].onError(new Error('network')))
    expect(screen.getByText('sold out')).toBeInTheDocument()
    expect(screen.queryByText('Nada para revisar agora')).not.toBeInTheDocument()
  })
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
      expect.objectContaining({ onSuccess: expect.any(Function) as unknown }) as unknown,
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
      courseSlug: 'voa-level-1',
      unitSlug: '45-49',
      itemType: 'grammar_error',
      skill: 'grammar',
      maxMinutes: 2,
    })
    expect(useSuspended).toHaveBeenLastCalledWith(
      { courseSlug: 'voa-level-1', unitSlug: '45-49' },
      undefined,
    )
  })

  it('mostra a identidade do curso no card e permite ampliar para todas as unidades', async () => {
    const user = userEvent.setup()
    useDueCards.mockReturnValue({ data: [carta], isPending: false, error: null })
    montar()

    expect(screen.getAllByText(/Let's Learn English — Level 1 · Aula 31/)).toHaveLength(2)
    await user.selectOptions(screen.getByLabelText('Unidade'), '')
    expect(useDueCards).toHaveBeenLastCalledWith(
      expect.objectContaining({ courseSlug: 'voa-level-1', unitSlug: undefined }) as unknown,
    )
  })

  it('reativa um item suspenso', async () => {
    const user = userEvent.setup()
    useDueCards.mockReturnValue({ data: [], isPending: false, error: null })
    useSuspended.mockReturnValue({
      data: { items: [{ ...carta, status: 'suspended' }], next_cursor: null },
      isPending: false,
      isFetching: false,
      error: null,
    })
    montar()

    await user.click(screen.getByRole('button', { name: 'Reativar' }))
    expect(setStatus).toHaveBeenCalledWith(
      { itemId: 7, status: 'active' },
      expect.objectContaining({ onSuccess: expect.any(Function) as unknown }) as unknown,
    )
  })

  it('carrega mais suspensos sem perder a página anterior e preserva o foco', async () => {
    const user = userEvent.setup()
    const older = { ...carta, id: 6, prompt: 'take a taxi', status: 'suspended' }
    const firstPage = { items: [{ ...carta, status: 'suspended' }], next_cursor: 'page-2' }
    const secondPage = { items: [older], next_cursor: null }
    useDueCards.mockReturnValue({ data: [], isPending: false, error: null })
    useSuspended.mockImplementation((_filters, cursor) => ({
      data: cursor ? secondPage : firstPage,
      isPending: false,
      isFetching: false,
      error: null,
    }))
    montar()

    expect(await screen.findByText('sold out')).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Carregar mais' }))

    expect(await screen.findByText('take a taxi')).toBeVisible()
    expect(screen.getByText('sold out')).toBeVisible()
    await waitFor(() => expect(screen.getByText('2 suspensos carregados.')).toHaveFocus())
    expect(useSuspended).toHaveBeenLastCalledWith(
      { courseSlug: 'voa-level-1', unitSlug: '45-49' },
      'page-2',
    )

    setStatus.mockImplementationOnce((_command, callbacks) => callbacks.onSuccess())
    await user.click(screen.getAllByRole('button', { name: 'Reativar' })[1]!)
    expect(screen.queryByText('take a taxi')).not.toBeInTheDocument()
    expect(screen.getByText('sold out')).toBeVisible()
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
        { cardId: 7, quality: 4, expectedRevision: 0, idempotencyKey: expect.any(String) as unknown },
        expect.objectContaining({ onSuccess: expect.any(Function) as unknown }) as unknown,
      ),
    )
  })

  it('não captura espaço ou enter usados no player de áudio', () => {
    useDueCards.mockReturnValue({
      data: [{ ...carta, media_url: 'https://example.com/review.mp3' }],
      isPending: false,
      error: null,
    })
    const { container } = montar()
    const audio = container.querySelector('audio[controls]')
    expect(audio).not.toBeNull()

    fireEvent.keyDown(audio!, { key: ' ' })
    fireEvent.keyDown(audio!, { key: 'Enter' })

    expect(screen.queryByText('esgotado')).toBeNull()
    expect(screen.getByRole('button', { name: 'Mostrar resposta' })).toBeInTheDocument()
  })

  it('"Errei" manda qualidade abaixo do corte de acerto', async () => {
    const user = userEvent.setup()
    useDueCards.mockReturnValue({ data: [carta], isPending: false, error: null })
    montar()

    await user.click(screen.getByRole('button', { name: 'Mostrar resposta' }))
    await user.click(screen.getByText('Errei'))

    expect(avaliar.mock.calls[0]![0]).toEqual({ cardId: 7, quality: 1, expectedRevision: 0, idempotencyKey: expect.any(String) as unknown })
  })

  it('deck vazio explica como encher', () => {
    useDueCards.mockReturnValue({ data: [], isPending: false, error: null })
    montar('/revisar?course=voa-level-1')
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
    expect(screen.getByRole('alert')).toHaveTextContent('Não foi possível carregar esta área agora.')
    expect(screen.getByRole('button', { name: 'Tentar de novo' })).toBeInTheDocument()
  })
})
