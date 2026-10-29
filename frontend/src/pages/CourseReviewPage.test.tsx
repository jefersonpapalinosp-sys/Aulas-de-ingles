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
        { id: 1, slug: '31-40', lessons: [{ number: 40 }] },
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
    skill: 'grammar',
    lesson_numbers: [31],
    prompt: 'Comparação. Complete: A taxi is ____ a bus.',
    options: ['faster than', 'more faster than', 'faster that'],
  },
  {
    id: 102,
    position: 2,
    activity_type: 'multiple_choice',
    skill: 'grammar',
    lesson_numbers: [32],
    prompt: 'Dois objetos. Complete: Kids from all over the world ask ____ questions.',
    options: ['us', 'we', 'our'],
  },
  {
    id: 103,
    position: 3,
    activity_type: 'multiple_choice',
    skill: 'grammar',
    lesson_numbers: [33],
    prompt: 'Presente simples e agente. Complete: First, the ____ pitches the ball to the batter.',
    options: ['pitcher', 'pitch', 'pitching'],
  },
  {
    id: 104,
    position: 4,
    activity_type: 'multiple_choice',
    skill: 'grammar',
    lesson_numbers: [34],
    prompt: "Possibilidade. Complete: I ____ go to the party; I'm not sure.",
    options: ['might', 'will definitely', 'might to'],
  },
  {
    id: 105,
    position: 5,
    activity_type: 'multiple_choice',
    skill: 'grammar',
    lesson_numbers: [35],
    prompt: 'Quantidade e embalagem. Qual frase está correta?',
    options: [
      'I bought two loaves of bread.',
      'I bought two loafs of bread.',
      'I bought too much loaves of bread.',
    ],
  },
  {
    id: 106,
    position: 6,
    activity_type: 'multiple_choice',
    skill: 'grammar',
    lesson_numbers: [36],
    prompt:
      'Lugar e concordância. Complete: Where ____ the eggs? They are inside the cabinet ____ the sink.',
    options: ['are; under', 'is; under', 'are; in'],
  },
  {
    id: 107,
    position: 7,
    activity_type: 'multiple_choice',
    skill: 'grammar',
    lesson_numbers: [37],
    prompt: 'Pronome possessivo. Complete: This is my bag. This bag is ____.',
    options: ['mine', 'my', 'me'],
  },
  {
    id: 108,
    position: 8,
    activity_type: 'multiple_choice',
    skill: 'grammar',
    lesson_numbers: [38],
    prompt: 'Superlativo. Complete: Old friends are ____.',
    options: ['the best', 'the goodest', 'better than'],
  },
  {
    id: 109,
    position: 9,
    activity_type: 'multiple_choice',
    skill: 'grammar',
    lesson_numbers: [39],
    prompt: 'Prefixo negativo. Reescreva not perfect com uma palavra: It is ____.',
    options: ['imperfect', 'unperfect', 'disperfect'],
  },
  {
    id: 110,
    position: 10,
    activity_type: 'multiple_choice',
    skill: 'listening',
    lesson_numbers: [40],
    prompt: 'Na escuta da Aula 40, como o diretor pede que Anna fale?',
    options: [
      'More loudly and more seriously.',
      'More quietly and more slowly.',
      'Earlier and less carefully.',
    ],
  },
]

const review: CourseReview = {
  id: 12,
  slug: 'checkpoint-31-40-level-1',
  position: 11,
  title: 'Fechamento 31–40',
  intro:
    'Feche o bloco revendo comparativos, objetos diretos e indiretos, presente simples, agentes em -er, possibilidade com might, certeza com will, quantidades, preposições de lugar, possessivos, superlativos, prefixos negativos e advérbios de modo. A escuta da Aula 40 verifica as orientações dadas a Anna durante o ensaio.',
  estimated_minutes: 18,
  question_count: 10,
  content_version: 1,
  review_lesson_number: 40,
  listening_lesson_number: 40,
  source_kind: 'authorial',
  source_title: 'Fechamento autoral do Aulas de Inglês',
  source_url: null,
  source_note:
    'Não há review oficial da VOA com o recorte exato das Aulas 31–40 do Level 1. As revisões oficiais 30–34, 35–39 e 40–44 sustentam, respectivamente, os objetivos das Aulas 31–34, 35–39 e 40; foram usadas apenas como referências curriculares. Este fechamento é inteiramente autoral — seleção de competências, perguntas, alternativas, explicações e correção — e não equivale a, nem substitui, uma revisão da VOA.',
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
    duration_seconds: 251,
    listening_exercise_position: null,
    cues: [],
    transcript: [],
  },
  questions,
}

const persistedAttempt: CourseReviewAttempt = {
  id: 501,
  content_version: 1,
  completed_at: '2026-10-08T12:00:00Z',
  score: 7,
  total: 10,
  score_percent: 70,
  status: 'reinforce',
  reinforced_lesson_numbers: [31, 40],
  feedback: [
    {
      question_id: 101,
      position: 1,
      answer: 'more faster than',
      correct: false,
      accepted_answers: ['faster than'],
      explanation: 'Fast é um adjetivo curto: o comparativo recebe -er e é seguido por than.',
      lesson_numbers: [31],
    },
  ],
}

function renderPage() {
  return render(
    <MemoryRouter
      initialEntries={['/cursos/voa-level-1/unidades/31-40/checkpoint']}
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
      initialEntries={['/cursos/voa-level-1/unidades/31-40/checkpoint']}
    >
      <Link to="/cursos/voa-level-1/unidades/40-44/checkpoint">
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
      'Não foi possível carregar esta área agora.',
    )
    await user.click(screen.getByRole('button', { name: 'Tentar de novo' }))
    expect(hooks.refetch).toHaveBeenCalledOnce()
  })

  it('mostra dez questões sem antecipar o gabarito, áudio e retorno à Aula 40', () => {
    renderPage()

    expect(screen.getByRole('heading', { name: 'Fechamento 31–40' })).toBeInTheDocument()
    expect(screen.getAllByRole('group')).toHaveLength(10)
    const provenance = screen.getByRole('region', { name: 'Origem do checkpoint' })
    expect(within(provenance).getByText('Origem')).toBeInTheDocument()
    expect(
      within(provenance).getByText('Fechamento autoral do Aulas de Inglês'),
    ).toBeInTheDocument()
    expect(within(provenance).queryByRole('link')).not.toBeInTheDocument()
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
    expect(screen.getByRole('progressbar', { name: 'Questões respondidas' })).toHaveAttribute(
      'aria-valuemax',
      '10',
    )
    expect(screen.getByRole('button', { name: 'Concluir checkpoint' })).toBeDisabled()
    expect(screen.getByRole('link', { name: 'Voltar à unidade' })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/unidades/31-40',
    )
    expect(
      screen.queryByText('faster than', { selector: 'small' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByText(/Fast é um adjetivo curto/),
    ).not.toBeInTheDocument()
  })

  it('só envia quando tudo foi respondido e reutiliza a idempotência nos reenvios', async () => {
    const user = userEvent.setup()
    renderPage()

    for (const question of questions) {
      const group = screen.getByRole('group', {
        name: (accessibleName) => accessibleName.includes(question.prompt),
      })
      await user.click(within(group).getAllByRole('radio')[0]!)
    }

    expect(screen.getByText('10/10 respondidas')).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Questões respondidas' })).toHaveAttribute(
      'aria-valuenow',
      '10',
    )
    const submit = screen.getByRole('button', { name: 'Concluir checkpoint' })
    expect(submit).toBeEnabled()
    await user.click(submit)
    await user.click(submit)

    const expectedAttempt = {
      idempotency_key: '123e4567-e89b-12d3-a456-426614174000',
      content_version: 1,
      answers: questions.map((question) => ({
        question_id: question.id,
        answer: question.options![0],
      })),
    }
    expect(hooks.mutate).toHaveBeenNthCalledWith(1, expectedAttempt)
    expect(hooks.mutate).toHaveBeenNthCalledWith(2, expectedAttempt)
    // eslint-disable-next-line @typescript-eslint/unbound-method -- Referência do spy para configuração/asserção, sem invocação sem receiver.
    expect(globalThis.crypto.randomUUID).toHaveBeenCalledOnce()
  })

  it('restaura e anuncia o resultado, depois inicia nova execução com foco e nova chave', async () => {
    // eslint-disable-next-line @typescript-eslint/unbound-method -- Referência do spy para configuração/asserção, sem invocação sem receiver.
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
    expect(screen.getByText('Você acertou 7 de 10 questões (70%).')).toBeInTheDocument()
    expect(screen.getByLabelText('70 por cento')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Aula 31' })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/aulas/31',
    )
    expect(screen.getByRole('link', { name: 'Aula 40' })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/aulas/40',
    )
    expect(screen.getByRole('link', { name: 'Continuar na Aula 41' })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/aulas/41',
    )
    expect(
      screen.getByText(
        (_, element) =>
          element?.tagName === 'SMALL' &&
          element.textContent?.includes(
            'resposta esperada: faster than',
          ) === true,
      ),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Concluir checkpoint' })).not.toBeInTheDocument()

    await userEvent.setup().click(screen.getByRole('button', { name: 'Refazer checkpoint' }))
    const firstAnswer = screen.getByRole('radio', {
      name: 'faster than',
    })
    await waitFor(() => expect(firstAnswer).toHaveFocus())

    const user = userEvent.setup()
    await user.click(firstAnswer)
    for (const question of questions.slice(1)) {
      const group = screen.getByRole('group', {
        name: (accessibleName) => accessibleName.includes(question.prompt),
      })
      await user.click(within(group).getAllByRole('radio')[0]!)
    }
    await user.click(screen.getByRole('button', { name: 'Concluir checkpoint' }))

    expect(hooks.mutate).toHaveBeenLastCalledWith(
      expect.objectContaining({
        idempotency_key: '223e4567-e89b-12d3-a456-426614174000',
      }) as unknown,
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
      screen.getByRole('link', { name: 'Ver progresso do curso' }),
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

    await user.click(screen.getByRole('radio', { name: 'faster than' }))
    expect(screen.getByText('1/10 respondidas')).toBeInTheDocument()

    await user.click(screen.getByRole('link', { name: 'Trocar checkpoint' }))

    expect(screen.getByRole('heading', { name: 'Checkpoint 40-44' })).toBeInTheDocument()
    expect(screen.getByText('0/10 respondidas')).toBeInTheDocument()
    expect(
      screen.getByRole('radio', { name: 'faster than' }),
    ).not.toBeChecked()
    // eslint-disable-next-line @typescript-eslint/unbound-method -- Referência do spy para configuração/asserção, sem invocação sem receiver.
    expect(globalThis.crypto.randomUUID).toHaveBeenCalledTimes(2)
    expect(hooks.useSubmitCourseReview).toHaveBeenLastCalledWith(
      'voa-level-1',
      '40-44',
    )
  })
})
