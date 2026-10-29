import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { LessonMedia } from '../../api/client'
import { ShadowingPractice } from './ShadowingPractice'
import { setAccessToken, setSessionReadOnly, setSessionUser } from '../../api/session'

const clientMocks = vi.hoisted(() => ({
  GET: vi.fn<(path: string, ...args: unknown[]) => Promise<unknown>>(),
  POST: vi.fn(),
  PUT: vi.fn(),
  DELETE: vi.fn(),
  authenticatedFetch: vi.fn<(url: string, options: RequestInit) => Promise<Partial<Response>>>(),
  policy: vi.fn<() => Promise<unknown>>(),
}))

vi.mock('../../api/client', () => ({
  api: {
    GET: (path: string, ...args: unknown[]) => path === '/api/speaking/policy'
      ? clientMocks.policy() : clientMocks.GET(path, ...args),
    POST: clientMocks.POST,
    PUT: clientMocks.PUT,
    DELETE: clientMocks.DELETE,
  },
  authenticatedFetch: clientMocks.authenticatedFetch,
}))

const media: LessonMedia = {
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
}

class FakeMediaRecorder {
  static isTypeSupported = () => true
  state: RecordingState = 'inactive'
  mimeType = 'audio/webm'
  ondataavailable: ((event: BlobEvent) => void) | null = null
  onstop: (() => void) | null = null

  start() {
    this.state = 'recording'
  }

  stop() {
    this.state = 'inactive'
    this.ondataavailable?.({ data: new Blob(['voice'], { type: this.mimeType }) } as BlobEvent)
    this.onstop?.()
  }
}

beforeEach(() => {
  setAccessToken('synthetic-token')
  setSessionUser(7)
  setSessionReadOnly(false)
  clientMocks.policy.mockResolvedValue({ data: { max_bytes: 2_000_000, max_duration_ms: 30_000,
    mime_types: ['audio/webm', 'audio/mp4', 'audio/ogg'], upload_timeout_seconds: 30 } })
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.clearAllMocks()
  window.localStorage.clear()
})

function renderPractice(courseSlug = 'voa-level-1', lessonNumber = 31) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = render(
    <StrictMode><QueryClientProvider client={queryClient}>
      <ShadowingPractice
        courseSlug={courseSlug}
        media={media}
        userId={7}
        lessonNumber={lessonNumber}
      />
    </QueryClientProvider></StrictMode>,
  )
  return { ...view, queryClient }
}

async function recordLocally() {
  vi.stubGlobal('MediaRecorder', FakeMediaRecorder)
  vi.stubGlobal('URL', { createObjectURL: vi.fn().mockReturnValue('blob:local-test'), revokeObjectURL: vi.fn() })
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true,
    value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }) } })
  const view = renderPractice()
  await userEvent.click(screen.getByRole('button', { name: '2. Gravar minha voz' }))
  await userEvent.click(await screen.findByRole('button', { name: 'Parar gravação' }))
  return view
}

describe('ShadowingPractice', () => {
  it.each(['missing', 'changed'])('preserva histórico e bloqueia reprodução de arquivo %s', async (integrity_state) => {
    clientMocks.GET.mockResolvedValue({ data: [{ id: 15, lesson_number: 31, cue_id: 21,
      cue_text: media.cues[0]!.text_en, historical_content_status: 'available',
      duration_ms: 1500, status: 'ready',
      integrity_state, mime_type: 'audio/webm', file_size: 5,
      created_at: '2026-10-07T23:50:00Z' }] })
    renderPractice()
    expect(await screen.findByText(/Arquivo ausente ou alterado/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ouvir' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Excluir' })).toBeEnabled()
    expect(clientMocks.authenticatedFetch).not.toHaveBeenCalled()
  })
  it.each([413, 415, 422, 401, 408, 409, 503])('preserva o áudio para ouvir/baixar e tentar novamente após HTTP %s', async (code) => {
    clientMocks.GET.mockResolvedValue({ data: [] })
    clientMocks.POST.mockResolvedValue({ data: { id: 44 } })
    clientMocks.authenticatedFetch.mockResolvedValueOnce({ ok: false, status: code })
    await recordLocally()
    await userEvent.click(screen.getByRole('checkbox', { name: /Concordo em salvar/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Salvar na minha conta' }))
    expect(await screen.findByText(/O áudio continua nesta tela; você pode baixá-lo/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Baixar gravação local' })).toHaveAttribute('href', 'blob:local-test')
    expect(clientMocks.DELETE).not.toHaveBeenCalled()
    clientMocks.authenticatedFetch.mockResolvedValueOnce({ ok: true })
    await userEvent.click(screen.getByRole('button', { name: 'Salvar na minha conta' }))
    expect(await screen.findByText(/Gravação salva na sua conta/)).toBeInTheDocument()
    expect(clientMocks.POST).toHaveBeenCalledOnce()
    expect(clientMocks.authenticatedFetch.mock.calls[0]![1].body).toBe(clientMocks.authenticatedFetch.mock.calls[1]![1].body)
  })
  it('não apaga tentativa após resposta perdida e reutiliza seu ID', async () => {
    clientMocks.GET.mockResolvedValue({ data: [] })
    clientMocks.POST.mockResolvedValue({ data: { id: 44 } })
    clientMocks.authenticatedFetch.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await recordLocally()
    await userEvent.click(screen.getByRole('checkbox', { name: /Concordo em salvar/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Salvar na minha conta' }))
    expect(await screen.findByText(/Falha de conexão/)).toBeInTheDocument()
    expect(clientMocks.DELETE).not.toHaveBeenCalled()
    clientMocks.authenticatedFetch.mockResolvedValueOnce({ ok: true })
    await userEvent.click(screen.getByRole('button', { name: 'Salvar na minha conta' }))
    expect(await screen.findByText(/Gravação salva na sua conta/)).toBeInTheDocument()
    expect(clientMocks.POST).toHaveBeenCalledOnce()
  })
  it('recupera envio após login na mesma conta, inclusive em StrictMode, sem consentir automaticamente', async () => {
    clientMocks.GET.mockResolvedValue({ data: [] })
    clientMocks.POST.mockResolvedValue({ data: { id: 44 } })
    const view = await recordLocally()
    clientMocks.authenticatedFetch.mockImplementationOnce(() => {
      setAccessToken(null); setSessionUser(null)
      view.unmount()
      return Promise.resolve({ ok: false, status: 401 })
    })
    await userEvent.click(screen.getByRole('checkbox', { name: /Concordo em salvar/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Salvar na minha conta' }))
    setAccessToken('new-token'); setSessionUser(7)
    let urlNumber = 0
    // eslint-disable-next-line @typescript-eslint/unbound-method -- Referência do spy para configuração/asserção, sem invocação sem receiver.
    vi.mocked(URL.createObjectURL).mockImplementation(() => `blob:recovered-${++urlNumber}`)
    const restoredView = renderPractice()
    expect(await screen.findByText(/Gravação recuperada nesta aba/)).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /Concordo em salvar/ })).not.toBeChecked()
    clientMocks.authenticatedFetch.mockResolvedValueOnce({ ok: true })
    await userEvent.click(screen.getByRole('checkbox', { name: /Concordo em salvar/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Salvar na minha conta' }))
    expect(await screen.findByText(/Gravação salva na sua conta/)).toBeInTheDocument()
    expect(clientMocks.POST).toHaveBeenCalledOnce()
    restoredView.unmount()
    expect(urlNumber).toBe(2) // setup/cleanup/setup do StrictMode
    for (let index = 1; index <= urlNumber; index++) {
      // eslint-disable-next-line @typescript-eslint/unbound-method -- Referência do spy para configuração/asserção, sem invocação sem receiver.
      expect(URL.revokeObjectURL).toHaveBeenCalledWith(`blob:recovered-${index}`)
    }
  })
  it('impede envio do blob em outra conta antes de criar tentativa', async () => {
    clientMocks.GET.mockResolvedValue({ data: [] })
    await recordLocally()
    setSessionUser(99)
    await userEvent.click(screen.getByRole('checkbox', { name: /Concordo em salvar/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Salvar na minha conta' }))
    expect(await screen.findByText(/Confirme a sessão da mesma conta/)).toBeInTheDocument()
    expect(clientMocks.POST).not.toHaveBeenCalled()
  })
  it('mantém gravação local mas bloqueia envio enquanto não confirma política', async () => {
    clientMocks.GET.mockResolvedValue({ data: [] })
    clientMocks.policy.mockRejectedValue(new Error('offline'))
    await recordLocally()
    await userEvent.click(screen.getByRole('checkbox', { name: /Concordo em salvar/ }))
    expect(screen.getByRole('button', { name: 'Salvar na minha conta' })).toBeDisabled()
    expect(screen.getByRole('link', { name: 'Baixar gravação local' })).toBeInTheDocument()
  })
  it('não anuncia autoavaliação salva quando quota falha', async () => {
    clientMocks.GET.mockResolvedValue({ data: [] })
    await recordLocally()
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('', 'QuotaExceededError') })
    await userEvent.click(screen.getByRole('button', { name: 'Confiante' }))
    expect(screen.getByRole('button', { name: 'Confiante' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText(/Autoavaliação apenas nesta tela/)).toBeInTheDocument()
    expect(screen.queryByText('Autoavaliação salva neste navegador.')).not.toBeInTheDocument()
  })
  it('leitura bloqueada não impede repetir e autoavaliar', async () => {
    clientMocks.GET.mockResolvedValue({ data: [] })
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new DOMException('', 'SecurityError') })
    await recordLocally()
    expect(screen.getByText(/Armazenamento indisponível/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Confiante' }))
    expect(screen.getByText('Autoavaliação salva neste navegador.')).toBeInTheDocument()
  })
  it('mantém a prática oral disponível quando a gravação não é suportada', () => {
    clientMocks.GET.mockResolvedValue({ data: [] })
    renderPractice()

    expect(screen.getByRole('heading', { name: 'Escute, repita e compare sua voz' })).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('não oferece gravação de áudio')
    expect(screen.getByRole('button', { name: '2. Gravar minha voz' })).toBeDisabled()
  })

  it('isola histórico e cache pela identidade composta de curso e aula', async () => {
    clientMocks.GET.mockResolvedValue({ data: [] })
    const { queryClient } = renderPractice('voa-level-2', 1)

    await waitFor(() =>
      expect(clientMocks.GET).toHaveBeenCalledWith('/api/speaking/attempts', {
        params: { query: { lesson: 1, course: 'voa-level-2' } },
      }),
    )
    expect(
      queryClient.getQueryState(['speaking-attempts', 7, 'voa-level-2', 1]),
    ).toBeDefined()
    expect(
      queryClient.getQueryState(['speaking-attempts', 7, 'voa-level-1', 1]),
    ).toBeUndefined()
  })

  it('reproduz o modelo, grava localmente e salva a autoavaliação', async () => {
    const user = userEvent.setup()
    const stopTrack = vi.fn()
    const getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [{ stop: stopTrack }] })
    const createObjectURL = vi.fn().mockReturnValue('blob:voice')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('MediaRecorder', FakeMediaRecorder)
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL })
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia },
    })
    const play = vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue()
    vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => undefined)
    clientMocks.GET.mockResolvedValue({ data: [] })
    clientMocks.POST.mockResolvedValue({
      data: {
        id: 44,
        lesson_number: 31,
        cue_id: 21,
        cue_text: media.cues[0]!.text_en,
        historical_content_status: 'available',
        duration_ms: 100,
        self_rating: 'confident',
        consented_at: '2026-10-07T23:50:00Z',
        status: 'pending',
        mime_type: null,
        file_size: null,
        created_at: '2026-10-07T23:50:00Z',
      },
    })
    clientMocks.authenticatedFetch.mockResolvedValue({ ok: true })
    const { container, queryClient } = renderPractice()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')

    await user.click(screen.getByRole('button', { name: '1. Ouvir modelo' }))
    expect(play).toHaveBeenCalledOnce()
    expect(container.querySelector('audio')?.currentTime).toBe(31)

    await user.click(screen.getByRole('button', { name: '2. Gravar minha voz' }))
    expect(await screen.findByRole('button', { name: 'Parar gravação' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Parar gravação' }))

    expect(getUserMedia).toHaveBeenCalledWith({ audio: true })
    expect(stopTrack).toHaveBeenCalledOnce()
    expect(createObjectURL).toHaveBeenCalledOnce()
    expect(container.querySelector('.shadowing-result audio')).toHaveAttribute('src', 'blob:voice')

    await user.click(screen.getByRole('button', { name: 'Confiante' }))
    expect(screen.getByRole('button', { name: 'Confiante' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(
      window.localStorage.getItem(
        'aulas-ingles:shadowing-rating:v2:7:voa-level-1:31:21',
      ),
    ).toBe(
      'confident',
    )

    const save = screen.getByRole('button', { name: 'Salvar na minha conta' })
    expect(save).toBeDisabled()
    await user.click(
      screen.getByRole('checkbox', {
        name: /Concordo em salvar esta gravação na minha conta/,
      }),
    )
    await user.click(save)

    await waitFor(() => expect(clientMocks.POST).toHaveBeenCalledOnce())
    expect(clientMocks.POST).toHaveBeenCalledWith('/api/speaking/attempts', {
      body: expect.objectContaining({ cue_id: 21, self_rating: 'confident', consent: true }) as unknown,
      signal: expect.any(AbortSignal) as unknown,
    })
    expect(clientMocks.authenticatedFetch).toHaveBeenCalledWith(
      '/api/speaking/attempts/44/audio',
      expect.objectContaining({ method: 'PUT', body: expect.any(Blob) as unknown }) as unknown,
    )
    expect(await screen.findByText(/Gravação salva na sua conta/)).toBeInTheDocument()
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['speaking-attempts'] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['course-completion'] })
  })

  it('reproduz e exclui somente uma gravação escolhida do histórico', async () => {
    const user = userEvent.setup()
    clientMocks.GET.mockResolvedValue({
      data: [
        {
          id: 15,
          lesson_number: 31,
          cue_id: 21,
          cue_text: media.cues[0]!.text_en,
          historical_content_status: 'available',
          duration_ms: 1500,
          self_rating: 'almost',
          consented_at: '2026-10-07T23:50:00Z',
          status: 'ready',
          mime_type: 'audio/webm',
          file_size: 5,
          created_at: '2026-10-07T23:50:00Z',
        },
      ],
    })
    clientMocks.authenticatedFetch.mockResolvedValue({
      ok: true,
      blob: vi.fn().mockResolvedValue(new Blob(['voice'], { type: 'audio/webm' })),
    })
    clientMocks.DELETE.mockResolvedValue({ response: { ok: true } })
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn().mockReturnValue('blob:saved-voice'),
      revokeObjectURL: vi.fn(),
    })
    const { queryClient } = renderPractice()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')

    expect(await screen.findByText('Quase lá', { exact: false })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Ouvir' }))
    expect(await screen.findByLabelText('Reprodução da gravação salva')).toHaveAttribute(
      'src',
      'blob:saved-voice',
    )

    await user.click(screen.getByRole('button', { name: 'Excluir' }))
    expect(clientMocks.DELETE).toHaveBeenCalledWith(
      '/api/speaking/attempts/{attempt_id}',
      { params: { path: { attempt_id: 15 } } },
    )
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ['course-completion'] }),
    )
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['assist-status'] })
  })

  it('não reconstrói trecho legado nem oferece nova comparação automática', async () => {
    clientMocks.GET.mockImplementation((path) =>
      Promise.resolve(path === '/api/assist/status'
        ? {
            data: {
              transcription_enabled: true,
              writing_enabled: false,
              evaluation_only: true,
              daily_quota: 5,
              used_today: 0,
              remaining_today: 5,
              retention_days: 30,
              cost_microusd_today: 0,
            },
          }
        : {
            data: [
              {
                id: 15,
                lesson_number: 31,
                cue_id: 21,
                cue_text: null,
                historical_content_status: 'unavailable',
                duration_ms: 1500,
                status: 'ready',
                integrity_state: 'verified',
                mime_type: 'audio/webm',
                file_size: 5,
                created_at: '2026-10-07T23:50:00Z',
              },
            ],
          }),
    )
    renderPractice()

    expect(await screen.findByText('Texto original indisponível')).toBeInTheDocument()
    expect(screen.getByText(/sem comparação automática/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Transcrever (experimental)' })).not.toBeInTheDocument()
  })

  it.each([0.42, null])('marca automação e confiança incerta (%s) na transcrição experimental', async (confidence) => {
    const user = userEvent.setup()
    const transcription = {
      id: 55,
      attempt_id: 15,
      status: 'completed',
      provider: 'provider-test',
      attempt_count: 1,
      max_attempts: 3,
      next_attempt_at: '2026-10-07T23:50:00Z',
      automated: true,
      evaluation_only: true,
      expected_text: media.cues[0]!.text_en,
      historical_content_status: 'available',
      transcript_text: "Don't take the boss",
      words: [
        { text: "Don't", start_ms: 0, end_ms: 100, confidence: 0.96 },
        { text: 'boss', start_ms: 101, end_ms: 200, confidence },
      ],
      mean_confidence: confidence === null ? null : 0.69,
      similarity_score: 0.78,
      low_confidence: true,
      error_code: null,
      cost_microusd: 1200,
      human_rating: null,
      requested_at: '2026-10-07T23:50:00Z',
      completed_at: '2026-10-07T23:50:02Z',
      expires_at: '2026-11-06T23:50:00Z',
    }
    clientMocks.GET.mockImplementation((path) =>
      Promise.resolve(path === '/api/assist/status'
        ? {
            data: {
              transcription_enabled: true,
              writing_enabled: false,
              evaluation_only: true,
              daily_quota: 5,
              used_today: 1,
              remaining_today: 4,
              retention_days: 30,
              cost_microusd_today: 1200,
            },
          }
        : {
            data: [
              {
                id: 15,
                lesson_number: 31,
                cue_id: 21,
                cue_text: media.cues[0]!.text_en,
                historical_content_status: 'available',
                duration_ms: 1500,
                self_rating: 'almost',
                consented_at: '2026-10-07T23:50:00Z',
                status: 'ready',
                mime_type: 'audio/webm',
                file_size: 5,
                created_at: '2026-10-07T23:50:00Z',
                transcription,
              },
            ],
          }),
    )
    clientMocks.PUT.mockResolvedValue({ data: { ...transcription, human_rating: 'helpful' } })
    renderPractice()

    expect(await screen.findByText('Automatizado · somente avaliação')).toBeInTheDocument()
    expect(screen.getByText(/Transcrição incerta: ouça sua gravação/)).toBeInTheDocument()
    expect(screen.getByText('boss')).toHaveClass('low-confidence')
    if (confidence === null) {
      expect(screen.getByText(/Confiança não informada/)).toBeInTheDocument()
      expect(screen.queryByText(/Confiança média 0%/)).not.toBeInTheDocument()
    }
    await user.click(screen.getByRole('button', { name: 'Sim' }))
    expect(clientMocks.PUT).toHaveBeenCalledWith(
      '/api/speaking/transcriptions/{job_id}/rating',
      { params: { path: { job_id: 55 } }, body: { rating: 'helpful' } },
    )
  })

  it('explica quando o worker agendou uma nova tentativa', async () => {
    clientMocks.GET.mockImplementation((path) =>
      Promise.resolve(path === '/api/assist/status'
        ? {
            data: {
              transcription_enabled: true,
              writing_enabled: false,
              evaluation_only: true,
              daily_quota: 5,
              used_today: 1,
              remaining_today: 4,
              retention_days: 30,
              cost_microusd_today: 0,
            },
          }
        : {
            data: [
              {
                id: 15,
                lesson_number: 31,
                cue_id: 21,
                cue_text: media.cues[0]!.text_en,
                historical_content_status: 'available',
                duration_ms: 1500,
                self_rating: 'almost',
                consented_at: '2026-10-07T23:50:00Z',
                status: 'ready',
                mime_type: 'audio/webm',
                file_size: 5,
                created_at: '2026-10-07T23:50:00Z',
                transcription: {
                  id: 55,
                  attempt_id: 15,
                  status: 'queued',
                  provider: 'provider-test',
                  attempt_count: 1,
                  max_attempts: 3,
                  next_attempt_at: '2026-10-07T23:50:05Z',
                  automated: true,
                  evaluation_only: true,
                  expected_text: media.cues[0]!.text_en,
                  historical_content_status: 'available',
                  transcript_text: null,
                  words: [],
                  mean_confidence: null,
                  similarity_score: null,
                  low_confidence: false,
                  error_code: 'provider_unavailable',
                  cost_microusd: 0,
                  human_rating: null,
                  requested_at: '2026-10-07T23:50:00Z',
                  completed_at: null,
                  expires_at: '2026-11-06T23:50:00Z',
                },
              },
            ],
          }),
    )

    renderPractice()

    expect(
      await screen.findByText(/Nova tentativa será feita automaticamente \(1 de 3 realizadas\)/),
    ).toBeInTheDocument()
  })
})
