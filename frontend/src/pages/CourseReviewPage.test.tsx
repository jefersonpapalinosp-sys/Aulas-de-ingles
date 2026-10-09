import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CourseReview, CourseReviewAttempt } from '../api/client'
import { CourseReviewPage } from './CourseReviewPage'

const hooks = vi.hoisted(() => ({
  useCourseReview: vi.fn(),
  useSubmitCourseReview: vi.fn(),
  refetch: vi.fn(),
  mutate: vi.fn(),
  reset: vi.fn(),
}))

vi.mock('../api/auth', () => ({
  useSessao: () => ({
    usuario: { id: 7, email: 'aluno@example.com', display_name: 'Aluno' },
    carregando: false,
  }),
}))

vi.mock('../api/courseReviews', () => ({
  useCourseReview: hooks.useCourseReview,
  useSubmitCourseReview: hooks.useSubmitCourseReview,
}))

vi.mock('../api/queries', () => ({
  useCourseCurriculum: () => ({
    data: {
      course: { title: "Let's Learn English — Level 1" },
      units: [
        { id: 2, slug: '40-44', lessons: [{ number: 41 }] },
        { id: 3, slug: '45-49', lessons: [{ number: 45 }] },
        { id: 4, slug: '50-52', lessons: [{ number: 50 }] },
      ],
    },
    isPending: false,
    error: null,
  }),
}))

vi.mock('../features/media/LessonAudioPlayer', () => ({
  LessonAudioPlayer: ({
    media,
    sourcePageUrl,
  }: {
    media: { label: string }
    sourcePageUrl: string
  }) => (
    <div data-testid="checkpoint-audio" data-source-page={sourcePageUrl}>
      Áudio carregado: {media.label}
    </div>
  ),
}))

const questions: CourseReview['questions'] = [
  {
    id: 101,
    position: 1,
    activity_type: 'multiple_choice',
    skill: 'listening',
    lesson_numbers: [40],
    prompt: 'O que Anna ouve na floresta?',
    options: ['Um pássaro', 'Um carro', 'Uma campainha'],
  },
  {
    id: 102,
    position: 2,
    activity_type: 'multiple_choice',
    skill: 'grammar',
    lesson_numbers: [41],
    prompt: 'Qual frase usa corretamente o pronome reflexivo?',
    options: ['She did it herself.', 'She did it her.', 'She herself did it is.'],
  },
  {
    id: 103,
    position: 3,
    activity_type: 'multiple_choice',
    skill: 'grammar',
    lesson_numbers: [42],
    prompt: 'Escolha a ação que estava em andamento.',
    options: ['I was reading.', 'I read tomorrow.', 'I am read.'],
  },
  {
    id: 104,
    position: 4,
    activity_type: 'multiple_choice',
    skill: 'vocabulary',
    lesson_numbers: [43],
    prompt: 'Qual opção significa plano alternativo?',
    options: ['Plan B', 'Team member', 'Healthy choice'],
  },
  {
    id: 105,
    position: 5,
    activity_type: 'multiple_choice',
    skill: 'grammar',
    lesson_numbers: [44],
    prompt: 'Qual conselho é adequado?',
    options: ['You should rest.', 'You rest yesterday.', 'You should to rest.'],
  },
  {
    id: 106,
    position: 6,
    activity_type: 'short_answer',
    skill: 'vocabulary',
    lesson_numbers: [40, 41, 42, 43, 44],
    prompt: 'Escreva a expressão para uma escolha saudável.',
    options: null,
  },
]

const review: CourseReview = {
  id: 12,
  slug: 'checkpoint-40-44',
  position: 5,
  title: 'Checkpoint 40–44',
  intro: 'Consolide listening, gramática e vocabulário antes de continuar.',
  estimated_minutes: 12,
  question_count: 6,
  content_version: 3,
  review_lesson_number: 40,
  listening_lesson_number: 40,
  source_kind: 'mixed',
  source_title: "VOA Let's Learn English — Level 1",
  source_url: 'https://learningenglish.voanews.com/p/5644.html',
  source_note: 'Base oficial da VOA; questões autorais deste projeto.',
  status: 'published',
  latest_attempt: null,
  listening_source_page_url: 'https://example.com/lesson-40',
  listening_media: {
    id: 40,
    kind: 'conversation_audio',
    label: 'Conversa da Aula 40',
    source_url: 'https://example.com/lesson-40.mp3',
    license_status: 'public_domain',
    license_url: 'https://learningenglish.voanews.com/p/5644.html',
    license_note: 'Produção da Voice of America.',
    attribution: 'Voice of America (VOA Learning English)',
    offline_policy: 'network_only',
    license_reviewed_at: '2026-10-08',
    duration_seconds: 180,
    listening_exercise_position: null,
    cues: [],
    transcript: [],
  },
  questions,
}

const persistedAttempt: CourseReviewAttempt = {
  id: 501,
  content_version: 3,
  completed_at: '2026-10-08T12:00:00Z',
  score: 4,
  total: 6,
  score_percent: 67,
  status: 'reinforce',
  reinforced_lesson_numbers: [40, 42],
  feedback: [
    {
      question_id: 101,
      position: 1,
      answer: 'Um carro',
      correct: false,
      accepted_answers: ['Um pássaro'],
      explanation: 'No trecho selecionado, Anna identifica o som de um pássaro.',
      lesson_numbers: [40],
    },
  ],
}

function renderPage() {
  return render(
    <MemoryRouter
      initialEntries={['/cursos/voa-level-1/unidades/40-44/checkpoint']}
    >
      <Routes>
        <Route
          path="/cursos/:courseSlug/unidades/:unitSlug/checkpoint"
          element={<CourseReviewPage />}
        />
      </Routes>
    </MemoryRouter>,
  )
}

function renderSwitchablePage() {
  return render(
    <MemoryRouter
      initialEntries={['/cursos/voa-level-1/unidades/40-44/checkpoint']}
    >
      <Link to="/cursos/voa-level-1/unidades/45-49/checkpoint">
        Trocar checkpoint
      </Link>
      <Routes>
        <Route
          path="/cursos/:courseSlug/unidades/:unitSlug/checkpoint"
          element={<CourseReviewPage />}
        />
      </Routes>
    </MemoryRouter>,
  )
}

function renderFinalPage() {
  return render(
    <MemoryRouter
      initialEntries={['/cursos/voa-level-1/unidades/50-52/checkpoint']}
    >
      <Routes>
        <Route
          path="/cursos/:courseSlug/unidades/:unitSlug/checkpoint"
          element={<CourseReviewPage />}
        />
      </Routes>
    </MemoryRouter>,
  )
}

describe('CourseReviewPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.clearAllMocks()
    hooks.useCourseReview.mockReturnValue({
      data: review,
      isPending: false,
      error: null,
      refetch: hooks.refetch,
    })
    hooks.useSubmitCourseReview.mockReturnValue({
      data: undefined,
      isPending: false,
      error: null,
      mutate: hooks.mutate,
      reset: hooks.reset,
    })
    vi.spyOn(globalThis.crypto, 'randomUUID').mockReturnValue(
      '123e4567-e89b-12d3-a456-426614174000',
    )
    Object.defineProperty(window, 'scrollTo', { value: vi.fn(), writable: true })
  })

  it('expõe estados de carregamento e recuperação de erro', async () => {
    const user = userEvent.setup()
    hooks.useCourseReview.mockReturnValueOnce({
      data: undefined,
      isPending: true,
      error: null,
      refetch: hooks.refetch,
    })
    const first = renderPage()

    expect(screen.getByRole('status')).toHaveTextContent(
      'Carregando o checkpoint da unidade',
    )
    first.unmount()

    hooks.useCourseReview.mockReturnValueOnce({
      data: undefined,
      isPending: false,
      error: new Error('Este checkpoint não existe nesta unidade.'),
      refetch: hooks.refetch,
    })
    renderPage()

    expect(screen.getByRole('alert')).toHaveTextContent(
      'Este checkpoint não existe nesta unidade.',
    )
    await user.click(screen.getByRole('button', { name: 'Tentar de novo' }))
    expect(hooks.refetch).toHaveBeenCalledOnce()
  })

  it('mostra seis questões sem antecipar o gabarito, áudio e retorno à Aula 40', () => {
    renderPage()

    expect(screen.getByRole('heading', { name: 'Checkpoint 40–44' })).toBeInTheDocument()
    expect(screen.getAllByRole('group')).toHaveLength(6)
    expect(screen.getByTestId('checkpoint-audio')).toHaveTextContent(
      'Conversa da Aula 40',
    )
    expect(screen.getByTestId('checkpoint-audio')).toHaveAttribute(
      'data-source-page',
      'https://example.com/lesson-40',
    )
    expect(screen.getByRole('link', { name: 'Rever Aula 40' })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/aulas/40',
    )
    expect(screen.getByRole('progressbar', { name: 'Questões respondidas' })).toHaveAttribute(
      'aria-valuenow',
      '0',
    )
    expect(screen.getByRole('button', { name: 'Concluir checkpoint' })).toBeDisabled()
    expect(screen.getByRole('link', { name: 'Voltar à unidade' })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/unidades/40-44',
    )
    expect(screen.queryByText('Um pássaro', { selector: 'small' })).not.toBeInTheDocument()
    expect(
      screen.queryByText(/No trecho selecionado, Anna identifica/),
    ).not.toBeInTheDocument()
  })

  it('só envia quando tudo foi respondido e reutiliza a idempotência nos reenvios', async () => {
    const user = userEvent.setup()
    renderPage()

    for (const question of questions.slice(0, 5)) {
      const group = screen.getByRole('group', { name: new RegExp(question.prompt) })
      await user.click(within(group).getAllByRole('radio')[0]!)
    }
    await user.type(
      screen.getByRole('textbox', {
        name: 'Resposta para: Escreva a expressão para uma escolha saudável.',
      }),
      'healthy choice',
    )

    expect(screen.getByText('6/6 respondidas')).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Questões respondidas' })).toHaveAttribute(
      'aria-valuenow',
      '6',
    )
    const submit = screen.getByRole('button', { name: 'Concluir checkpoint' })
    expect(submit).toBeEnabled()
    await user.click(submit)
    await user.click(submit)

    const expectedAttempt = {
      idempotency_key: '123e4567-e89b-12d3-a456-426614174000',
      content_version: 3,
      answers: [
        { question_id: 101, answer: 'Um pássaro' },
        { question_id: 102, answer: 'She did it herself.' },
        { question_id: 103, answer: 'I was reading.' },
        { question_id: 104, answer: 'Plan B' },
        { question_id: 105, answer: 'You should rest.' },
        { question_id: 106, answer: 'healthy choice' },
      ],
    }
    expect(hooks.mutate).toHaveBeenNthCalledWith(1, expectedAttempt)
    expect(hooks.mutate).toHaveBeenNthCalledWith(2, expectedAttempt)
    expect(globalThis.crypto.randomUUID).toHaveBeenCalledOnce()
  })

  it('restaura e anuncia o resultado, depois inicia nova execução com foco e nova chave', async () => {
    vi.mocked(globalThis.crypto.randomUUID)
      .mockReset()
      .mockReturnValueOnce('123e4567-e89b-12d3-a456-426614174000')
      .mockReturnValueOnce('223e4567-e89b-12d3-a456-426614174000')
    hooks.useCourseReview.mockReturnValue({
      data: { ...review, latest_attempt: persistedAttempt },
      isPending: false,
      error: null,
      refetch: hooks.refetch,
    })
    renderPage()

    const resultTitle = screen.getByRole('heading', { name: 'Vale reforçar alguns pontos' })
    expect(resultTitle).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Vale reforçar alguns pontos' })).toBeInTheDocument()
    await waitFor(() => expect(resultTitle).toHaveFocus())
    expect(screen.getByText('Você acertou 4 de 6 questões (67%).')).toBeInTheDocument()
    expect(screen.getByLabelText('67 por cento')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Aula 40' })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/aulas/40',
    )
    expect(screen.getByRole('link', { name: 'Aula 42' })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/aulas/42',
    )
    expect(screen.getByRole('link', { name: 'Continuar na Aula 45' })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/aulas/45',
    )
    expect(
      screen.getByText(
        (_, element) =>
          element?.tagName === 'SMALL' &&
          element.textContent?.includes('resposta esperada: Um pássaro') === true,
      ),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Concluir checkpoint' })).not.toBeInTheDocument()

    await userEvent.setup().click(screen.getByRole('button', { name: 'Refazer checkpoint' }))
    const firstAnswer = screen.getByRole('radio', { name: 'Um pássaro' })
    await waitFor(() => expect(firstAnswer).toHaveFocus())

    const user = userEvent.setup()
    await user.click(firstAnswer)
    for (const question of questions.slice(1, 5)) {
      const group = screen.getByRole('group', { name: new RegExp(question.prompt) })
      await user.click(within(group).getAllByRole('radio')[0]!)
    }
    await user.type(
      screen.getByRole('textbox', {
        name: 'Resposta para: Escreva a expressão para uma escolha saudável.',
      }),
      'healthy choice',
    )
    await user.click(screen.getByRole('button', { name: 'Concluir checkpoint' }))

    expect(hooks.mutate).toHaveBeenLastCalledWith(
      expect.objectContaining({
        idempotency_key: '223e4567-e89b-12d3-a456-426614174000',
      }),
    )
  })

  it('leva o resultado do último checkpoint ao fechamento do curso', () => {
    hooks.useCourseReview.mockReturnValue({
      data: {
        ...review,
        slug: 'checkpoint-50-52',
        title: 'Checkpoint 50–52',
        latest_attempt: persistedAttempt,
      },
      isPending: false,
      error: null,
      refetch: hooks.refetch,
    })

    renderFinalPage()

    expect(
      screen.getByRole('link', { name: 'Ver conclusão do curso' }),
    ).toHaveAttribute('href', '/cursos/voa-level-1/conclusao')
    expect(
      screen.queryByRole('link', { name: /Continuar na Aula/ }),
    ).not.toBeInTheDocument()
  })

  it('isola respostas e idempotência ao trocar diretamente de checkpoint', async () => {
    const user = userEvent.setup()
    hooks.useCourseReview.mockImplementation((_courseSlug: string, unitSlug: string) => ({
      data: {
        ...review,
        slug: `checkpoint-${unitSlug}`,
        title: `Checkpoint ${unitSlug}`,
      },
      isPending: false,
      error: null,
      refetch: hooks.refetch,
    }))
    renderSwitchablePage()

    await user.click(screen.getByRole('radio', { name: 'Um pássaro' }))
    expect(screen.getByText('1/6 respondidas')).toBeInTheDocument()

    await user.click(screen.getByRole('link', { name: 'Trocar checkpoint' }))

    expect(screen.getByRole('heading', { name: 'Checkpoint 45-49' })).toBeInTheDocument()
    expect(screen.getByText('0/6 respondidas')).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Um pássaro' })).not.toBeChecked()
    expect(globalThis.crypto.randomUUID).toHaveBeenCalledTimes(2)
    expect(hooks.useSubmitCourseReview).toHaveBeenLastCalledWith(
      'voa-level-1',
      '45-49',
    )
  })
})
