import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Exercise } from '../../api/client'
import type { PracticeSession } from './types'
import { PracticeRunner } from './PracticeRunner'

const practiceApi = vi.hoisted(() => ({
  exercises: vi.fn(),
  active: vi.fn(),
  session: vi.fn(),
  create: vi.fn(),
  position: vi.fn(),
}))

vi.mock('../../api/practice', () => ({
  usePracticeExercises: practiceApi.exercises,
  useActivePracticeSession: practiceApi.active,
  usePracticeSession: practiceApi.session,
  useCreatePracticeSession: practiceApi.create,
  useUpdatePracticePosition: practiceApi.position,
}))

const exercises = [
  {
    id: 101,
    position: 0,
    activity_type: 'gap_fill',
    skill: 'grammar',
    objective: 'apply',
    options: null,
    prompt: 'The blue ball is `____` than the red ball.',
    hint: null,
    hint_count: 2,
    explanation: null,
  },
  {
    id: 102,
    position: 1,
    activity_type: 'multiple_choice',
    skill: 'grammar',
    objective: 'recognize',
    options: ['faster', 'more fast'],
    prompt: 'Choose the correct comparative.',
    hint: null,
    hint_count: 1,
    explanation: null,
  },
] as unknown as Exercise[]

function makeSession(overrides: Partial<PracticeSession> = {}): PracticeSession {
  return {
    id: 71,
    course_slug: 'voa-level-1',
    unit_slug: '31-40',
    lesson_number: 31,
    lesson_title: 'Take Me Out to the Ball Game',
    content_version: 2,
    mode: 'guided',
    status: 'active',
    activity_type: null,
    skill: null,
    objective: null,
    content_changed: false,
    current_position: 0,
    state_revision: 1,
    started_at: '2026-10-08T12:00:00Z',
    updated_at: '2026-10-08T12:00:00Z',
    completed_at: null,
    summary: {
      total: 2,
      completed: 0,
      first_try_correct: 0,
      corrected: 0,
      revealed: 0,
      pending: 2,
    },
    items: exercises.map((exercise, position) => ({
      position,
      exercise,
      attempt_count: 0,
      first_try_correct: null,
      highest_hint_level: 0,
      opened_hints: [],
      answer_revealed: false,
      completed_at: null,
      outcome: 'pending',
      last_feedback: null,
      answers: null,
      explanation: null,
    })),
    ...overrides,
  }
}

function makeNavigableSession(overrides: Partial<PracticeSession> = {}): PracticeSession {
  const session = makeSession()
  return {
    ...session,
    summary: { ...session.summary, completed: 1, first_try_correct: 1, pending: 1 },
    items: session.items.map((item, index) =>
      index === 0
        ? {
            ...item,
            attempt_count: 1,
            first_try_correct: true,
            completed_at: '2026-10-08T12:01:00Z',
            outcome: 'first_try_correct' as const,
            explanation: 'Resposta correta.',
          }
        : item,
    ),
    ...overrides,
  }
}

function queryResult<T>(data: T, error: Error | null = null) {
  return {
    data,
    error,
    isPending: false,
    refetch: vi.fn().mockResolvedValue({ data }),
  }
}

function renderRunner() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PracticeRunner
          courseSlug="voa-level-1"
          lessonNumber={31}
          lessonTitle="Take Me Out to the Ball Game"
          userId={7}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  const active = queryResult<PracticeSession | null>(null)
  const session = makeSession()
  practiceApi.exercises.mockImplementation(
    (_course: string, _lesson: number, filters: { objective?: string } = {}) =>
      queryResult(filters.objective ? exercises.slice(1) : exercises),
  )
  practiceApi.active.mockReturnValue(active)
  practiceApi.session.mockReturnValue(queryResult(session))
  practiceApi.create.mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue(session),
    isPending: false,
    isError: false,
    error: null,
  })
  practiceApi.position.mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue(session),
    isPending: false,
  })
})

afterEach(() => {
  Object.defineProperty(window.navigator, 'onLine', { value: true, configurable: true })
  window.localStorage.clear()
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

describe('PracticeRunner', () => {
  it('expõe o estado de carregamento sem montar controles prematuramente', () => {
    practiceApi.active.mockReturnValue({
      data: undefined,
      error: null,
      isPending: true,
      refetch: vi.fn(),
    })
    renderRunner()

    expect(screen.getByRole('status')).toHaveTextContent('Carregando o laboratório')
    expect(screen.queryByRole('button', { name: /Começar/ })).toBeNull()
  })

  it('mostra erro acionável e tenta recarregar as fontes', async () => {
    const user = userEvent.setup()
    const activeRefetch = vi.fn()
    const exercisesRefetch = vi.fn()
    practiceApi.active.mockReturnValue({
      data: undefined,
      error: new Error('API indisponível.'),
      isPending: false,
      refetch: activeRefetch,
    })
    practiceApi.exercises.mockReturnValue({
      data: undefined,
      error: null,
      isPending: false,
      refetch: exercisesRefetch,
    })
    renderRunner()

    expect(screen.getByRole('alert')).toHaveTextContent('API indisponível.')
    await user.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    expect(activeRefetch).toHaveBeenCalled()
    expect(exercisesRefetch).toHaveBeenCalled()
  })

  it('mostra modos, filtros e o total real sem esconder o tamanho do pack', async () => {
    const user = userEvent.setup()
    renderRunner()

    expect(screen.getByRole('heading', { name: 'Escolha como praticar' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /Prática guiada/ })).toBeChecked()
    expect(screen.getByRole('radio', { name: /Repetir meus erros/ })).toBeDisabled()
    expect(screen.getByText('2 de 2 atividades disponíveis neste recorte.')).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Objetivo'), 'recognize')
    expect(screen.getByText('1 de 2 atividades disponíveis neste recorte.')).toBeInTheDocument()
  })

  it('inicia desafio rápido com filtros e chave idempotente', async () => {
    const user = userEvent.setup()
    const mutateAsync = vi.fn().mockResolvedValue(makeSession({ mode: 'quick' }))
    practiceApi.create.mockReturnValue({
      mutateAsync,
      isPending: false,
      isError: false,
      error: null,
    })
    renderRunner()

    await user.click(screen.getByRole('radio', { name: /Desafio rápido/ }))
    await user.selectOptions(screen.getByLabelText('Objetivo'), 'recognize')
    await user.click(screen.getByRole('button', { name: 'Começar Desafio rápido' }))

    expect(mutateAsync).toHaveBeenCalledWith({
      idempotency_key: expect.any(String),
      mode: 'quick',
      objective: 'recognize',
    })
  })

  it('oferece retomada e move o foco para o enunciado atual', async () => {
    const user = userEvent.setup()
    const session = makeSession({ current_position: 1 })
    practiceApi.active.mockReturnValue(queryResult(session))
    practiceApi.session.mockReturnValue(queryResult(session))
    renderRunner()

    expect(screen.getByRole('heading', { name: 'Continue de onde parou' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retomar sessão' }))

    const prompt = await screen.findByRole('heading', { name: /Choose the correct comparative/ })
    await waitFor(() => expect(prompt).toHaveFocus())
    expect(screen.getByText('Questão 2 de 2')).toBeInTheDocument()
  })

  it('preserva a resposta digitada quando o refetch registra uma dica aberta', async () => {
    const user = userEvent.setup()
    const session = makeSession()
    practiceApi.active.mockReturnValue(queryResult(session))
    practiceApi.session.mockReturnValue(queryResult(session))
    renderRunner()

    await user.click(screen.getByRole('button', { name: 'Retomar sessão' }))
    await user.type(screen.getByRole('textbox'), 'more fast')

    const refreshed = makeSession({
      state_revision: 2,
      items: session.items.map((item, index) =>
        index === 0
          ? {
              ...item,
              highest_hint_level: 1,
              opened_hints: [{ level: 1, content: 'Use o comparativo curto.' }],
            }
          : item,
      ),
    })
    practiceApi.session.mockReturnValue(queryResult(refreshed))
    await act(async () => {
      Object.defineProperty(window.navigator, 'onLine', { value: false, configurable: true })
      window.dispatchEvent(new Event('offline'))
    })

    expect(screen.getByRole('textbox')).toHaveValue('more fast')
  })

  it('preserva a nova resposta quando o refetch atualiza o número de tentativas', async () => {
    const user = userEvent.setup()
    const base = makeSession()
    const attempted = makeSession({
      state_revision: 2,
      items: base.items.map((item, index) =>
        index === 0
          ? {
              ...item,
              attempt_count: 1,
              first_try_correct: false,
              last_feedback: {
                category: 'extra_word',
                message: 'Há uma palavra ou estrutura a mais.',
                tokens: [{ text: 'more', status: 'review' }],
              },
            }
          : item,
      ),
    })
    practiceApi.active.mockReturnValue(queryResult(attempted))
    practiceApi.session.mockReturnValue(queryResult(attempted))
    renderRunner()

    await user.click(screen.getByRole('button', { name: 'Retomar sessão' }))
    await user.click(screen.getByRole('button', { name: 'Tentar novamente' }))
    await user.type(screen.getByRole('textbox'), 'faster')

    const refreshed = makeSession({
      state_revision: 3,
      items: attempted.items.map((item, index) =>
        index === 0 ? { ...item, attempt_count: 2 } : item,
      ),
    })
    practiceApi.session.mockReturnValue(queryResult(refreshed))
    await act(async () => {
      Object.defineProperty(window.navigator, 'onLine', { value: false, configurable: true })
      window.dispatchEvent(new Event('offline'))
    })

    expect(screen.getByRole('textbox')).toHaveValue('faster')
  })

  it('mantém tentativa offline fora do total concluído e permite avançar localmente', async () => {
    const user = userEvent.setup()
    Object.defineProperty(window.navigator, 'onLine', { value: false, configurable: true })
    window.dispatchEvent(new Event('offline'))
    const session = makeSession()
    practiceApi.active.mockReturnValue(queryResult(session))
    practiceApi.session.mockReturnValue(queryResult(session))
    renderRunner()

    await user.click(screen.getByRole('button', { name: 'Retomar sessão' }))
    await user.type(screen.getByRole('textbox'), 'bigger')
    await user.click(screen.getByRole('button', { name: 'Verificar' }))

    expect(await screen.findByText('Na fila')).toBeInTheDocument()
    const progress = screen.getByRole('progressbar', {
      name: 'Progresso da sessão de exercícios',
    })
    expect(progress).toHaveAttribute('aria-valuenow', '0')
    expect(progress).toHaveAttribute('aria-valuetext', expect.stringContaining('1 aguardando correção'))
    expect(screen.getByRole('button', { name: 'Próxima →' })).toBeEnabled()
  })

  it('sincroniza a posição local ao voltar online mesmo sem tentativa na fila', async () => {
    const user = userEvent.setup()
    Object.defineProperty(window.navigator, 'onLine', { value: false, configurable: true })
    const session = makeNavigableSession()
    const mutateAsync = vi.fn().mockResolvedValue(
      makeNavigableSession({ current_position: 1, state_revision: 2 }),
    )
    practiceApi.active.mockReturnValue(queryResult(session))
    practiceApi.session.mockReturnValue(queryResult(session))
    practiceApi.position.mockReturnValue({ mutateAsync, isPending: false })
    renderRunner()

    await user.click(screen.getByRole('button', { name: 'Retomar sessão' }))
    await user.click(screen.getByRole('button', { name: 'Próxima →' }))
    expect(mutateAsync).not.toHaveBeenCalled()
    expect(localStorage.getItem('aulas-ingles:practice-position:v1:7:71')).toBe('1')

    await act(async () => {
      Object.defineProperty(window.navigator, 'onLine', { value: true, configurable: true })
      window.dispatchEvent(new Event('online'))
    })

    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({
        sessionId: 71,
        currentPosition: 1,
        expectedRevision: 1,
        idempotencyKey: expect.any(String),
      }),
    )
    await waitFor(() =>
      expect(localStorage.getItem('aulas-ingles:practice-position:v1:7:71')).toBeNull(),
    )
  })

  it('envia um único PUT ao navegar enquanto está online', async () => {
    const user = userEvent.setup()
    const session = makeNavigableSession()
    const mutateAsync = vi.fn().mockResolvedValue(
      makeNavigableSession({ current_position: 1, state_revision: 2 }),
    )
    practiceApi.active.mockReturnValue(queryResult(session))
    practiceApi.session.mockReturnValue(queryResult(session))
    practiceApi.position.mockReturnValue({ mutateAsync, isPending: false })
    renderRunner()

    await user.click(screen.getByRole('button', { name: 'Retomar sessão' }))
    await user.click(screen.getByRole('button', { name: 'Próxima →' }))

    await waitFor(() =>
      expect(localStorage.getItem('aulas-ingles:practice-position:v1:7:71')).toBeNull(),
    )
    expect(mutateAsync).toHaveBeenCalledTimes(1)
    expect(mutateAsync).toHaveBeenCalledWith({
      sessionId: 71,
      currentPosition: 1,
      expectedRevision: 1,
      idempotencyKey: expect.any(String),
    })
  })

  it('refaz o PUT com a mesma chave após conflito de revisão', async () => {
    const user = userEvent.setup()
    const session = makeNavigableSession()
    const latest = makeNavigableSession({ state_revision: 2 })
    const refetch = vi.fn().mockResolvedValue({ data: latest })
    const mutateAsync = vi
      .fn()
      .mockRejectedValueOnce(new Error('conflito de revisão'))
      .mockResolvedValueOnce(makeNavigableSession({ current_position: 1, state_revision: 3 }))
    practiceApi.active.mockReturnValue(queryResult(session))
    practiceApi.session.mockReturnValue({ ...queryResult(session), refetch })
    practiceApi.position.mockReturnValue({ mutateAsync, isPending: false })
    renderRunner()

    await user.click(screen.getByRole('button', { name: 'Retomar sessão' }))
    await user.click(screen.getByRole('button', { name: 'Próxima →' }))

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(2))
    const first = mutateAsync.mock.calls[0]?.[0]
    const second = mutateAsync.mock.calls[1]?.[0]
    if (!first || !second) throw new Error('Os dois PUTs de posição não foram observados.')
    expect(first).toMatchObject({ expectedRevision: 1, currentPosition: 1 })
    expect(second).toMatchObject({ expectedRevision: 2, currentPosition: 1 })
    expect(second.idempotencyKey).toBe(first.idempotencyKey)
    expect(localStorage.getItem('aulas-ingles:practice-position:v1:7:71')).toBeNull()
  })

  it('mostra resumo separando primeira tentativa, correção e revelação', async () => {
    const user = userEvent.setup()
    const completed = makeSession({
      status: 'completed',
      completed_at: '2026-10-08T12:10:00Z',
      summary: {
        total: 2,
        completed: 2,
        first_try_correct: 1,
        corrected: 0,
        revealed: 1,
        pending: 0,
      },
    })
    const mutateAsync = vi.fn().mockResolvedValue(completed)
    practiceApi.create.mockReturnValue({
      mutateAsync,
      isPending: false,
      isError: false,
      error: null,
    })
    practiceApi.session.mockReturnValue(queryResult(completed))
    renderRunner()

    await user.click(screen.getByRole('button', { name: 'Começar Prática guiada' }))
    expect(await screen.findByRole('heading', { name: 'Resumo da sua prática' })).toBeInTheDocument()
    expect(screen.getByText('Primeira tentativa').nextSibling).toHaveTextContent('1')
    expect(screen.getByText('Respostas reveladas').nextSibling).toHaveTextContent('1')
    expect(screen.getByRole('button', { name: 'Repetir somente erros' })).toBeEnabled()
    expect(screen.getByRole('link', { name: 'Ir para revisão' })).toHaveAttribute('href', '/revisar')
  })

  it('bloqueia sessão com versão alterada e oferece recomeço seguro', async () => {
    const user = userEvent.setup()
    const stale = makeSession({ content_changed: true, skill: 'grammar' })
    const mutateAsync = vi.fn().mockResolvedValue(makeSession())
    practiceApi.active.mockReturnValue(queryResult(stale))
    practiceApi.create.mockReturnValue({
      mutateAsync,
      isPending: false,
      isError: false,
      error: null,
    })
    renderRunner()

    expect(
      screen.getByRole('heading', { name: 'Os exercícios mudaram desde o início desta sessão' }),
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Recomeçar com conteúdo atualizado' }))
    expect(mutateAsync).toHaveBeenCalledWith({
      idempotency_key: expect.any(String),
      mode: 'guided',
      skill: 'grammar',
    })
  })

  it('trata pack vazio com retorno para a aula', () => {
    practiceApi.exercises.mockReturnValue(queryResult([]))
    renderRunner()

    expect(screen.getByRole('heading', { name: 'Esta aula ainda não possui exercícios' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Voltar à aula' })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/aulas/31',
    )
  })
})
