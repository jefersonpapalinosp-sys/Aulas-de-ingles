import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CourseCompletion } from '../api/client'
import { CourseCompletionPage } from './CourseCompletionPage'

const hooks = vi.hoisted(() => ({
  useCourseCompletion: vi.fn(),
  refetch: vi.fn(),
}))

vi.mock('../api/completion', () => ({
  useCourseCompletion: hooks.useCourseCompletion,
}))

const completionData: CourseCompletion = {
  course: {
    slug: 'voa-level-1',
    title: "Let's Learn English — Level 1",
    level: '1',
    proficiency_label: 'Iniciante',
  },
  progress: {
    published_lessons: 22,
    viewed_lessons: 18,
    completed_lessons: 17,
    completion_percent: 77,
    status: 'in_progress',
  },
  incomplete_units: [
    {
      slug: '50-52',
      title: 'Aulas 50–52',
      published_lessons: 3,
      viewed_lessons: 2,
      completed_lessons: 1,
      href: '/cursos/voa-level-1/unidades/50-52',
    },
  ],
  checkpoints: {
    published: 3,
    current_completed: 2,
    pending: [
      {
        unit_slug: '50-52',
        title: 'Checkpoint 50–52',
        content_version: 2,
        href: '/cursos/voa-level-1/unidades/50-52/checkpoint',
      },
    ],
  },
  skills: [
    {
      skill: 'grammar',
      label: 'Gramática',
      samples: 2,
      score_percent: null,
      status: 'insufficient',
      fragile_topics: ['present perfect'],
    },
    {
      skill: 'listening',
      label: 'Compreensão oral',
      samples: 6,
      score_percent: 83,
      status: 'strong',
      fragile_topics: [],
    },
  ],
  certificate: {
    eligible: false,
    status: 'ineligible',
    reason: 'Conclua 5 aulas do recorte para liberar o certificado.',
    required_lessons: 22,
    required_checkpoints: 3,
    scope_label: 'Aulas 31–52',
    cta_label: 'Continuar estudando',
    cta_href: '/cursos/voa-level-1/unidades/50-52',
    automatic_download: false,
  },
  next_course: {
    slug: 'voa-level-2',
    title: "Let's Learn English — Level 2",
    level: '2',
    proficiency_label: 'Intermediário',
    status: 'planned',
    recommended: true,
    required: false,
    href: '/cursos/voa-level-2',
    preview: "Let's Learn English — Level 2 · Intermediário, por VOA Learning English.",
    diagnostic: {
      title: "Preparação para Let's Learn English — Level 2",
      description: 'Faça uma autoavaliação curta antes de decidir se quer começar.',
      href: '/cursos/voa-level-1/conclusao#diagnostico',
    },
  },
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/cursos/voa-level-1/conclusao']}>
      <Routes>
        <Route path="/cursos/:courseSlug/conclusao" element={<CourseCompletionPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('CourseCompletionPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    hooks.useCourseCompletion.mockReturnValue({
      data: completionData,
      isPending: false,
      error: null,
      refetch: hooks.refetch,
    })
  })

  it('apresenta carregamento e erro recuperável', async () => {
    const user = userEvent.setup()
    hooks.useCourseCompletion.mockReturnValueOnce({
      data: undefined,
      isPending: true,
      error: null,
      refetch: hooks.refetch,
    })
    const view = renderPage()

    expect(screen.getByRole('status')).toHaveTextContent('Carregando a conclusão do curso')

    view.unmount()
    hooks.useCourseCompletion.mockReturnValueOnce({
      data: undefined,
      isPending: false,
      error: new Error('Não foi possível buscar a conclusão.'),
      refetch: hooks.refetch,
    })
    renderPage()

    expect(screen.getByRole('alert')).toHaveTextContent('Não foi possível buscar a conclusão.')
    await user.click(screen.getByRole('button', { name: 'Tentar de novo' }))
    expect(hooks.refetch).toHaveBeenCalledOnce()
  })

  it('separa publicação, visualização, conclusão e competência por evidências', () => {
    const { container } = renderPage()

    expect(
      screen.getByRole('heading', { name: /Conclusão de Let's Learn English/ }),
    ).toHaveFocus()
    expect(screen.getByText('Conteúdo publicado').closest('div')).toHaveTextContent(
      '22Aulas disponíveis neste recorte',
    )
    expect(screen.getByText('Aulas vistas').closest('div')).toHaveTextContent(
      '18 / 22Sessão de estudo iniciada',
    )
    expect(screen.getByText('Aulas concluídas').closest('div')).toHaveTextContent(
      '17 / 22Somente aulas marcadas como estudadas',
    )
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '77')

    const grammar = screen.getByText('Gramática').closest('li')
    expect(grammar).not.toBeNull()
    expect(within(grammar!).getByText('Dados insuficientes (2/3)')).toBeInTheDocument()
    expect(within(grammar!).queryByText(/%/)).not.toBeInTheDocument()

    const listening = screen.getByText('Compreensão oral').closest('li')
    expect(listening).not.toBeNull()
    expect(within(listening!).getByText('Consistente · 83%')).toBeInTheDocument()
    expect(container.querySelector('iframe')).not.toBeInTheDocument()
    expect(container.querySelector('[download]')).not.toBeInTheDocument()
  })

  it('mantém unidades e checkpoint pendentes acessíveis por links canônicos', () => {
    renderPage()

    expect(screen.getByRole('link', { name: /Aulas 50–52/ })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/unidades/50-52',
    )
    expect(screen.getByRole('link', { name: /Checkpoint 50–52/ })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/unidades/50-52/checkpoint',
    )
    expect(screen.getByText(/continuam acessíveis para estudo e revisão/)).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: 'Certificado do recorte: ainda não elegível' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Continuar estudando' })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/unidades/50-52',
    )
  })

  it('oferece Level 2 como recomendado e opcional e orienta sem gerar nota', async () => {
    const user = userEvent.setup()
    renderPage()

    expect(screen.getByText('Recomendado e opcional.')).toBeInTheDocument()
    expect(screen.getByText(/Level 2 · Intermediário · Em preparação/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Conhecer Level 2' })).toHaveAttribute(
      'href',
      '/cursos/voa-level-2',
    )
    const diagnosticLink = screen.getByRole('link', { name: 'Fazer autoavaliação antes' })
    expect(diagnosticLink).toHaveAttribute(
      'href',
      '/cursos/voa-level-1/conclusao#diagnostico',
    )

    const diagnostic = screen
      .getByRole('heading', { name: "Preparação para Let's Learn English — Level 2" })
      .closest('section')
    expect(diagnostic).not.toBeNull()
    expect(within(diagnostic!).getByText(/não é prova, não gera nota/)).toBeInTheDocument()
    await user.click(diagnosticLink)
    expect(diagnostic).toHaveFocus()
    const submit = within(diagnostic!).getByRole('button', { name: 'Ver orientação' })
    expect(submit).toBeDisabled()

    for (const option of within(diagnostic!).getAllByLabelText('Em parte')) {
      await user.click(option)
    }
    expect(submit).toBeEnabled()
    await user.click(submit)

    expect(
      within(diagnostic!).getByRole('heading', {
        name: 'Explore Level 2 mantendo revisões',
      }),
    ).toHaveFocus()
    expect(within(diagnostic!).queryByText(/\d+ pontos|\d+%/i)).not.toBeInTheDocument()
  })

  it('mostra elegibilidade sem iniciar download quando tudo atual está concluído', () => {
    hooks.useCourseCompletion.mockReturnValue({
      data: {
        ...completionData,
        progress: {
          published_lessons: 22,
          viewed_lessons: 22,
          completed_lessons: 22,
          completion_percent: 100,
          status: 'completed',
        },
        incomplete_units: [],
        checkpoints: { published: 3, current_completed: 3, pending: [] },
        certificate: {
          ...completionData.certificate,
          eligible: true,
          status: 'eligible',
          reason: 'As 22 aulas do recorte e os 3 checkpoints atuais foram concluídos.',
          cta_label: 'Consultar revisão e certificado na VOA',
          cta_href:
            'https://learningenglish.voanews.com/a/lets-learn-english-review-lessons-50-51-52/3805506.html',
        },
      },
      isPending: false,
      error: null,
      refetch: hooks.refetch,
    })
    const { container } = renderPage()

    expect(
      screen.getByRole('heading', { name: 'Certificado do recorte: elegível' }),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Todas as unidades publicadas têm suas aulas concluídas.'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Todos os checkpoints publicados foram realizados na versão atual.'),
    ).toBeInTheDocument()
    expect(screen.getByText(/Nenhum certificado é baixado automaticamente/)).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'Consultar revisão e certificado na VOA' }),
    ).toHaveAttribute('target', '_blank')
    expect(screen.getByText(/escopo “Aulas 31–52”/)).toBeInTheDocument()
    expect(screen.getByText(/A página externa da VOA considera o curso oficial completo/))
      .toBeInTheDocument()
    expect(container.querySelector('[download]')).not.toBeInTheDocument()
  })

  it('trata curso sem aulas publicadas como estado vazio e preserva acesso', () => {
    hooks.useCourseCompletion.mockReturnValue({
      data: {
        ...completionData,
        progress: {
          published_lessons: 0,
          viewed_lessons: 0,
          completed_lessons: 0,
          completion_percent: 0,
          status: 'not_started',
        },
        incomplete_units: [],
        checkpoints: { published: 0, current_completed: 0, pending: [] },
        skills: [],
      },
      isPending: false,
      error: null,
      refetch: hooks.refetch,
    })
    renderPage()

    expect(
      screen.getByRole('heading', { name: 'Ainda não há aulas publicadas neste curso' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ver mapa do curso' })).toHaveAttribute(
      'href',
      '/cursos/voa-level-1',
    )
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })
})
