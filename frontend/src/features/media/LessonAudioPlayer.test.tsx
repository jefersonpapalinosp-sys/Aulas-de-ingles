import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { LessonMedia } from '../../api/client'
import { formatAudioTime, LessonAudioPlayer } from './LessonAudioPlayer'

const savePosition = vi.fn()
const clearPosition = vi.fn()

vi.mock('../../api/media', () => ({
  useMediaPosition: () => ({ data: null }),
  useSaveMediaPosition: () => ({
    mutate: savePosition,
    isError: false,
    isSuccess: false,
  }),
  useClearMediaPosition: () => ({ mutate: clearPosition }),
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
  transcript: [
    { position: 0, speaker: 'Jonathan', text_en: 'Do not take the bus.' },
    { position: 1, speaker: 'Anna', text_en: 'A taxi is faster than a bus.' },
  ],
}

const sourcePageUrl = 'https://learningenglish.voanews.com/a/lesson-31/123.html'

afterEach(() => {
  window.localStorage.clear()
  savePosition.mockClear()
  clearPosition.mockClear()
})

describe('LessonAudioPlayer', () => {
  it('mostra o áudio oficial com duração conhecida', () => {
    const { container } = render(
      <LessonAudioPlayer media={media} userId={7} sourcePageUrl={sourcePageUrl} />,
    )

    expect(screen.getByRole('heading', { name: media.label })).toBeInTheDocument()
    expect(screen.getByText('0:00 / 3:29')).toBeInTheDocument()
    expect(container.querySelector('source')).toHaveAttribute('src', media.source_url)
    expect(screen.getByText('Fonte, licença e uso offline')).toBeInTheDocument()
    expect(screen.getByText(/o aplicativo não armazena este áudio no cache/)).toBeInTheDocument()

    const audio = container.querySelector('audio')
    if (!audio) throw new Error('elemento de áudio não renderizado')
    window.localStorage.setItem('aulas-ingles:media-position:v1:7:9', '42')
    Object.defineProperty(audio, 'duration', { value: 209, configurable: true })
    fireEvent.loadedMetadata(audio)
    expect(audio.currentTime).toBe(42)
    expect(screen.getByText('0:42 / 3:29')).toBeInTheDocument()
  })

  it('abre a transcrição, navega até o trecho e revela a tradução', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <LessonAudioPlayer media={media} userId={7} sourcePageUrl={sourcePageUrl} />,
    )
    const audio = container.querySelector('audio')
    const cue = media.cues[0]
    if (!audio) throw new Error('elemento de áudio não renderizado')
    if (!cue) throw new Error('trecho de teste não configurado')

    await user.click(screen.getByRole('button', { name: 'Mostrar transcrição' }))
    expect(screen.getByText(cue.text_en)).toBeInTheDocument()
    expect(screen.queryByText(cue.text_pt)).not.toBeInTheDocument()

    await user.click(screen.getByLabelText('Mostrar apoio em português'))
    expect(screen.getByText(cue.text_pt)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Ir para 0:31/ }))
    expect(audio.currentTime).toBe(31)
    expect(screen.getByText('0:31 / 3:29')).toBeInTheDocument()
  })

  it('abre a transcrição integral e credita a página oficial', async () => {
    const user = userEvent.setup()
    render(<LessonAudioPlayer media={media} userId={7} sourcePageUrl={sourcePageUrl} />)

    expect(screen.queryByText(media.transcript[0]?.text_en ?? '')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Mostrar texto integral' }))

    expect(screen.getByText(media.transcript[0]?.text_en ?? '')).toBeInTheDocument()
    expect(screen.getByText(media.transcript[1]?.text_en ?? '')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'VOA Learning English' })).toHaveAttribute(
      'href',
      sourcePageUrl,
    )
  })

  it('avança, muda a velocidade e marca um trecho A-B', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <LessonAudioPlayer media={media} userId={7} sourcePageUrl={sourcePageUrl} />,
    )
    const audio = container.querySelector('audio')
    if (!audio) throw new Error('elemento de áudio não renderizado')

    audio.currentTime = 10
    fireEvent.timeUpdate(audio)
    await user.click(screen.getByRole('button', { name: '+5 s' }))
    expect(audio.currentTime).toBe(15)
    fireEvent.pause(audio)
    expect(savePosition).toHaveBeenCalledWith(15)

    await user.selectOptions(screen.getByLabelText('Velocidade do áudio'), '1.25')
    expect(audio.playbackRate).toBe(1.25)

    await user.click(screen.getByRole('button', { name: 'Marcar início A' }))
    audio.currentTime = 20
    fireEvent.timeUpdate(audio)
    await user.click(screen.getByRole('button', { name: 'Marcar fim B' }))
    expect(screen.getByText('A 0:15 · B 0:20')).toBeInTheDocument()
  })

  it('limpa a retomada local e remota ao terminar', () => {
    const { container } = render(
      <LessonAudioPlayer media={media} userId={7} sourcePageUrl={sourcePageUrl} />,
    )
    const audio = container.querySelector('audio')
    if (!audio) throw new Error('elemento de áudio não renderizado')
    window.localStorage.setItem('aulas-ingles:media-position:v1:7:9', '200')

    fireEvent.ended(audio)

    expect(window.localStorage.getItem('aulas-ingles:media-position:v1:7:9')).toBeNull()
    expect(clearPosition).toHaveBeenCalledOnce()
  })

  it('formata tempo sem deixar valores inválidos escaparem', () => {
    expect(formatAudioTime(0)).toBe('0:00')
    expect(formatAudioTime(65.9)).toBe('1:05')
    expect(formatAudioTime(Number.NaN)).toBe('0:00')
  })
})
