import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { StrictMode } from 'react'
import { api } from '../../api/client'
import DialogueWorkspace from './DialogueWorkspace'
import { DialogueEntry } from './DialogueEntry'
import { dialogueFixture, lessonFixture, policyFixture, statusFixture, turnFixture } from './dialogueFixtures'
import type { DialogueTransport } from './dialogueTransport'

const callbacks = vi.hoisted(() => ({ finished: null as null | ((blob: Blob, duration: number) => void), cancel: vi.fn() }))
vi.mock('../speaking/voiceRecorder', () => ({ VoiceRecorder: class {
  constructor(cbs: { finished: (blob: Blob, duration: number) => void }) { callbacks.finished = cbs.finished }
  start = vi.fn()
  stop = vi.fn()
  cancel = callbacks.cancel
} }))
vi.mock('../../api/client', () => ({ api: { GET: vi.fn() } }))

beforeEach(() => {
  vi.mocked(api.GET).mockImplementation((path) => Promise.resolve({ data: path === '/api/speaking/policy' ? policyFixture : statusFixture, response: new Response() }))
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
  URL.createObjectURL = vi.fn(() => 'blob:synthetic')
  URL.revokeObjectURL = vi.fn()
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

function setup() {
  const dialogue = dialogueFixture()
  const transport = {
    session: () => ({ usuarioId: 3, token: 'synthetic', geracao: 1, perfilNaoConfirmado: false }),
    create: vi.fn<DialogueTransport['create']>((body) => { dialogue.mode = body.mode; return Promise.resolve({ ...dialogue }) }),
    read: vi.fn<DialogueTransport['read']>(() => Promise.resolve({ ...dialogue })),
    text: vi.fn<DialogueTransport['text']>((_id, pos, body) => {
      dialogue.turns = [{ ...turnFixture(pos), transcript: body.text }]; dialogue.turns_remaining--
      return Promise.resolve()
    }),
    audio: vi.fn<DialogueTransport['audio']>(() => {
      dialogue.turns = [{ ...turnFixture(), input_kind: 'audio', words: [{ text: 'bus', start_ms: 0, end_ms: 500, confidence: 0.6 }] }]
      return Promise.resolve()
    }),
    rate: vi.fn<DialogueTransport['rate']>((_id, _pos, rating) => { dialogue.turns[0]!.human_rating = rating; return Promise.resolve() }),
    remove: vi.fn<DialogueTransport['remove']>(() => Promise.resolve(undefined)),
  } satisfies DialogueTransport
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = render(<StrictMode><QueryClientProvider client={queryClient}>
    <DialogueWorkspace lesson={lessonFixture} userId={3} transport={transport} />
  </QueryClientProvider></StrictMode>)
  return { ...view, transport, dialogue, user: userEvent.setup() }
}
async function open(user: ReturnType<typeof userEvent.setup>, guided = false) {
  await waitFor(() => expect(screen.getByRole('button', { name: 'Iniciar conversa' })).toBeEnabled())
  if (guided) await user.selectOptions(screen.getByLabelText('Modo'), 'guided')
  await user.click(screen.getByRole('button', { name: 'Iniciar conversa' }))
  await screen.findByLabelText('Sua resposta em inglês')
}

it('Roteiro funciona sem microfone e mantém resposta em texto com foco previsível', async () => {
  const { user, transport } = setup()
  await open(user)
  const input = screen.getByLabelText('Sua resposta em inglês')
  await user.type(input, 'I take the bus.')
  await user.click(screen.getByRole('button', { name: 'Enviar texto' }))
  expect(await screen.findByText('Where do you go?')).toBeInTheDocument()
  expect(input).toHaveFocus()
  expect(input).toHaveValue('')
  expect(screen.queryByRole('button', { name: 'Gravar resposta' })).not.toBeInTheDocument()
  expect(transport.text).toHaveBeenCalledWith(7, 1, expect.objectContaining({ idempotency_key: expect.any(String) as unknown }) as unknown, expect.any(AbortSignal) as unknown)
})

it('Guiado exige consentimento por gravação, mostra confiança e permite avaliação e exclusão', async () => {
  const { user, transport } = setup()
  await open(user, true)
  await user.click(await screen.findByRole('button', { name: 'Gravar resposta' }))
  act(() => callbacks.finished!(new Blob(['audio'], { type: 'audio/webm' }), 1000))
  const consent = screen.getByRole('checkbox')
  expect(consent).not.toBeChecked()
  expect(screen.getByRole('button', { name: 'Enviar áudio' })).toBeDisabled()
  await user.click(consent)
  await user.click(screen.getByRole('button', { name: 'Enviar áudio' }))
  expect(await screen.findByText('(transcrição incerta)')).toBeInTheDocument()
  await waitFor(() => expect(screen.getByLabelText('Sua resposta em inglês')).toHaveFocus())
  expect(screen.getByText('Automatizado, em avaliação')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: /^Foi útil$/ }))
  await waitFor(() => expect(screen.getByRole('button', { name: /^Foi útil$/ })).toHaveAttribute('aria-pressed', 'true'))
  await user.click(screen.getByRole('button', { name: 'Excluir conversa' }))
  expect(transport.remove).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Confirmar exclusão' }))
  await screen.findByRole('button', { name: 'Iniciar conversa' })
  expect(transport.remove).toHaveBeenCalledOnce()
  // eslint-disable-next-line @typescript-eslint/unbound-method -- Referência do spy para asserção; não há chamada sem receiver.
  expect(URL.revokeObjectURL).toHaveBeenCalled()
})

it('bloqueia gravação acima do teto e mantém opção de baixar', async () => {
  const { user, transport } = setup()
  await open(user, true)
  act(() => callbacks.finished!(new Blob([new Uint8Array(2_000_001)], { type: 'audio/webm' }), 1000))
  await user.click(screen.getByRole('checkbox'))
  expect(screen.getByRole('button', { name: 'Enviar áudio' })).toBeDisabled()
  expect(screen.getByRole('link', { name: 'Baixar gravação' })).toBeInTheDocument()
  expect(transport.audio).not.toHaveBeenCalled()
})

it('offline preserva o rascunho e impede envio até a conexão voltar', async () => {
  const { user, transport } = setup()
  await open(user)
  await user.type(screen.getByLabelText('Sua resposta em inglês'), 'Keep this draft')
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
  fireEvent(window, new Event('offline'))
  expect(screen.getByRole('button', { name: 'Enviar texto' })).toBeDisabled()
  expect(screen.getByLabelText('Sua resposta em inglês')).toHaveValue('Keep this draft')
  expect(transport.text).not.toHaveBeenCalled()
})

it('oculta a entrada e não abre diálogo quando a flag está desligada', async () => {
  vi.mocked(api.GET).mockResolvedValue({ data: { ...statusFixture, enabled: false }, response: new Response() })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><DialogueEntry userId={3} lesson={lessonFixture} /></QueryClientProvider>)
  await waitFor(() => expect(api.GET).toHaveBeenCalled())
  expect(screen.queryByRole('button', { name: 'Abrir parceiro de conversa' })).not.toBeInTheDocument()
})


it('parar durante o pedido de permissão cancela o microfone e libera o texto', async () => {
  const { user } = setup()
  await open(user, true)
  await user.click(await screen.findByRole('button', { name: 'Gravar resposta' }))
  const previous = callbacks.cancel.mock.calls.length
  await user.click(screen.getByRole('button', { name: 'Parar gravação' }))
  expect(callbacks.cancel.mock.calls.length).toBe(previous + 1)
  expect(screen.getByLabelText('Sua resposta em inglês')).toBeEnabled()
})
