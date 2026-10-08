import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { studyProgressKey } from '../features/study-session/studyProgress'
import { StudyPage } from './StudyPage'

const marcarEstudada = vi.fn()
const salvarSessao = vi.fn()

vi.mock('../api/auth', () => ({
  useSessao: () => ({
    usuario: { id: 7, email: 'aluno@example.com', display_name: 'Aluno' },
    carregando: false,
  }),
}))

vi.mock('../api/progress', () => ({
  useStudySession: () => ({
    data: {
      lesson_number: 31,
      current_step: 'preparar',
      completed_steps: [],
      started_at: null,
      updated_at: null,
      completed_at: null,
      total_seconds: 0,
    },
    isPending: false,
    error: null,
  }),
  useSalvarStudySession: () => ({
    mutate: salvarSessao,
    isPending: false,
    isError: false,
    isSuccess: true,
  }),
  useMarcarEstudada: () => ({
    mutate: marcarEstudada,
    isPending: false,
    isError: false,
    error: null,
  }),
}))

const lesson = {
  id: 31,
  course_slug: 'voa-level-1',
  unit_slug: '31-40',
  slug: 'take-me-out-to-the-ball-game',
  position: 31,
  number: 31,
  title: 'Take Me Out to the Ball Game',
  title_pt: 'Leve-me ao jogo de beisebol',
  voa_url: 'https://example.com/lesson-31',
  grammar_tag: 'Comparativos + conselho',
  focus_points: ['faster than'],
  story_note: null,
  lead: 'Compare transportes e dê conselhos.',
  warmup_prompt: 'Como você compararia duas formas de transporte?',
  listening_focus: 'os transportes comparados e o conselho final',
  goals: ['Comparar duas coisas com **-er than**.', 'Dar conselho com **should**.'],
  grammar_blocks: [],
  versions: [
    {
      version: 1,
      status: 'reviewed',
      learning_strategy: 'visualizar',
      review_note: 'Revisada.',
      reviewed_at: '2026-10-08T00:00:00Z',
      published_at: null,
    },
  ],
  media: [
    {
      id: 9,
      kind: 'conversation_audio',
      label: 'Conversa da Aula 31',
      source_url: 'https://audio.example.com/lesson-31.mp3',
      license_status: 'public_domain',
      license_url: 'https://learningenglish.voanews.com/p/6021.html',
      license_note: 'Produção exclusiva da VOA em domínio público.',
      attribution: 'Voice of America (VOA Learning English)',
      offline_policy: 'network_only',
      license_reviewed_at: '2026-10-08',
      duration_seconds: 209,
      listening_exercise_position: 6,
      cues: [
        {
          id: 21,
          position: 0,
          start_seconds: 31,
          end_seconds: 38,
          speaker: 'Jonathan',
          text_en: "Don't take the bus. A taxi is faster than a bus.",
          text_pt: 'Não pegue o ônibus. Um táxi é mais rápido que um ônibus.',
        },
      ],
      transcript: [],
    },
  ],
  phrases: [
    {
      text_en: 'A taxi is faster than a bus.',
      text_pt: 'Um táxi é mais rápido que um ônibus.',
      note: 'Observe **faster than**.',
    },
  ],
  vocab: [],
  pronunciation: [],
  writing_prompts: [
    {
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
    },
  ],
  exercises: [
    {
      id: 17,
      position: 6,
      activity_type: 'multiple_choice',
      skill: 'listening',
      objective: 'listen',
      options: ['bus', 'taxi', 'Metro'],
      prompt: 'Listening: Anna finalmente pega o `____`.',
      hint: 'ouça primeiro',
      hint_count: 2,
      explanation: 'Ela pega o Metro.',
    },
  ],
}

let lessonFixture = lesson

vi.mock('../api/queries', () => ({
  useLesson: () => ({ data: lessonFixture, isPending: false, error: null, refetch: vi.fn() }),
}))

vi.mock('../features/writing/WritingWorkspace', () => ({
  WritingWorkspace: () => <div>Área de escrita guiada</div>,
}))

vi.mock('../features/practice/PracticeRunner', () => ({
  PracticeRunner: ({ variant }: { variant?: string }) => (
    <div data-testid="shared-practice-runner">Runner compartilhado · {variant}</div>
  ),
}))

function renderStudy(route: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route
            path="/cursos/:courseSlug/aulas/:numero/estudar"
            element={<StudyPage />}
          />
          <Route
            path="/cursos/:courseSlug/aulas/:numero/estudar/:etapa"
            element={<StudyPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  lessonFixture = lesson
  window.localStorage.clear()
  vi.clearAllMocks()
})

describe('StudyPage', () => {
  it('apresenta a aula como uma jornada de cinco etapas', () => {
    renderStudy('/cursos/voa-level-1/aulas/31/estudar/preparar')

    expect(screen.getByRole('heading', { name: 'Take Me Out to the Ball Game' })).toBeInTheDocument()
    const navigation = screen.getByRole('navigation', { name: 'Etapas desta aula' })
    expect(navigation).toBeInTheDocument()
    expect(within(navigation).getAllByRole('listitem')).toHaveLength(5)
    expect(screen.getByText('Etapa 1 de 5')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'O que você vai conseguir fazer' })).toBeInTheDocument()
  })

  it('conclui a etapa, avança e persiste o ponto de retomada', async () => {
    const user = userEvent.setup()
    Object.defineProperty(window, 'scrollTo', { value: vi.fn(), writable: true })
    renderStudy('/cursos/voa-level-1/aulas/31/estudar/preparar')

    await user.click(screen.getByRole('button', { name: /Concluir e ir para Assistir/i }))

    expect(screen.getByText('Etapa 2 de 5')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Escute primeiro pelo contexto' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Conversa da Aula 31' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Escute e responda antes de ler' })).toBeInTheDocument()
    expect(JSON.parse(window.localStorage.getItem(studyProgressKey(7, 31)) ?? '{}')).toEqual({
      currentStep: 'assistir',
      completedSteps: ['preparar'],
    })
    expect(salvarSessao).toHaveBeenLastCalledWith({
      current_step: 'assistir',
      completed_steps: ['preparar'],
    })
  })

  it('retoma automaticamente a última etapa ao abrir a rota base', async () => {
    window.localStorage.setItem(
      studyProgressKey(7, 31),
      JSON.stringify({ currentStep: 'estudar', completedSteps: ['preparar', 'assistir'] }),
    )
    renderStudy('/cursos/voa-level-1/aulas/31/estudar')

    expect(await screen.findByText('Etapa 3 de 5')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Comparativos + conselho' })).toBeInTheDocument()
  })

  it('conclui a jornada e marca a aula como estudada no servidor', async () => {
    const user = userEvent.setup()
    window.localStorage.setItem(
      studyProgressKey(7, 31),
      JSON.stringify({
        currentStep: 'revisar',
        completedSteps: ['preparar', 'assistir', 'estudar', 'praticar'],
      }),
    )
    renderStudy('/cursos/voa-level-1/aulas/31/estudar/revisar')

    expect(
      screen.getByRole('heading', { name: 'Escute, repita e compare sua voz' }),
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Concluir aula' }))

    expect(marcarEstudada).toHaveBeenCalledWith({ numero: 31, estudada: true })
    expect(screen.getByRole('status')).toHaveTextContent(
      'Você percorreu as cinco etapas da Aula 31',
    )
  })

  it('oferece recuperação quando a etapa da URL não existe', () => {
    renderStudy('/cursos/voa-level-1/aulas/31/estudar/inexistente')

    expect(screen.getByRole('alert')).toHaveTextContent('Esta etapa de estudo não existe.')
    expect(screen.getByRole('link', { name: 'Retomar a aula' })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/aulas/31/estudar',
    )
  })

  it('reutiliza o runner do laboratório na etapa Praticar', () => {
    window.localStorage.setItem(
      studyProgressKey(7, 31),
      JSON.stringify({
        currentStep: 'praticar',
        completedSteps: ['preparar', 'assistir', 'estudar'],
      }),
    )
    renderStudy('/cursos/voa-level-1/aulas/31/estudar/praticar')

    expect(screen.getByTestId('shared-practice-runner')).toHaveTextContent(
      'Runner compartilhado · embedded',
    )
  })

  it('oferece listening textual utilizável quando mídia e coleções estão vazias', async () => {
    lessonFixture = {
      ...lesson,
      goals: [],
      grammar_blocks: [],
      media: [],
      phrases: [],
      vocab: [],
      pronunciation: [],
      writing_prompts: [],
      exercises: [],
    }
    renderStudy('/cursos/voa-level-1/aulas/31/estudar/assistir')

    expect(
      await screen.findByRole('heading', {
        name: 'Áudio não disponível neste aplicativo',
      }),
    ).toBeInTheDocument()
    expect(screen.getByRole('note')).toHaveTextContent('Resumo: Compare transportes e dê conselhos.')
    expect(screen.getByRole('note')).toHaveTextContent(
      'Crie uma frase curta em inglês usando o foco indicado acima.',
    )
    expect(screen.getByRole('link', { name: 'Abrir a aula na VOA ↗' })).toHaveAttribute(
      'href',
      'https://example.com/lesson-31',
    )
    expect(screen.queryByRole('audio')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Leia primeiro pelo contexto' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Frases para acompanhar' })).not.toBeInTheDocument()
    expect(
      screen.queryByRole('heading', { name: 'Escute e responda antes de ler' }),
    ).not.toBeInTheDocument()
  })

  it('oferece tarefas textuais nas etapas sem teoria, exercícios ou revisão enriquecida', async () => {
    lessonFixture = {
      ...lesson,
      goals: [],
      grammar_blocks: [],
      media: [],
      phrases: [],
      vocab: [],
      pronunciation: [],
      writing_prompts: [],
      exercises: [],
    }

    const theory = renderStudy('/cursos/voa-level-1/aulas/31/estudar/estudar')
    expect(
      await screen.findByRole('heading', { name: 'Estudo textual alternativo' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('note')).toHaveTextContent(
      'Escreva duas frases sobre esse contexto usando Comparativos + conselho',
    )
    theory.unmount()

    const practice = renderStudy('/cursos/voa-level-1/aulas/31/estudar/praticar')
    expect(
      await screen.findByRole('heading', { name: 'Prática textual alternativa' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('note')).toHaveTextContent(
      'Como você compararia duas formas de transporte?',
    )
    practice.unmount()

    renderStudy('/cursos/voa-level-1/aulas/31/estudar/revisar')
    expect(
      await screen.findByRole('heading', { name: 'Revisão textual rápida' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('note')).toHaveTextContent(
      'Crie um novo exemplo com Comparativos + conselho.',
    )
  })
})
