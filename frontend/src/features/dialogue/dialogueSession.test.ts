import { afterEach, describe, expect, it, vi } from 'vitest'
import { DialogueSession } from './dialogueSession'
import { DialogueError, type DialogueTransport } from './dialogueTransport'
import { dialogueFixture, policyFixture, turnFixture } from './dialogueFixtures'

function setup() {
  const account = { usuarioId: 3, token: 'synthetic', geracao: 1, perfilNaoConfirmado: false }
  const dialogue = dialogueFixture()
  const transport = {
    session: () => account,
    create: vi.fn<DialogueTransport['create']>(() => Promise.resolve(dialogue)), read: vi.fn<DialogueTransport['read']>(() => Promise.resolve(dialogue)),
    text: vi.fn<DialogueTransport['text']>(() => Promise.resolve({})), audio: vi.fn<DialogueTransport['audio']>(() => Promise.resolve({})),
    rate: vi.fn<DialogueTransport['rate']>(() => Promise.resolve({})), remove: vi.fn<DialogueTransport['remove']>(() => Promise.resolve(undefined)),
  } satisfies DialogueTransport
  const engine = new DialogueSession(3, transport, 10)
  return { account, dialogue, transport, engine }
}
afterEach(() => vi.useRealTimers())

describe('sessão da conversa', () => {
  it('conserva operation_key quando a criação perde a resposta', async () => {
    const { engine, transport } = setup()
    transport.create.mockRejectedValueOnce(new Error('network'))
    await engine.open(31, 'guided', null)
    const first = transport.create.mock.calls[0]
    await engine.open(31, 'guided', null)
    expect(transport.create.mock.calls[1]).toEqual([first![0], expect.any(AbortSignal) as unknown])
    expect(engine.snapshot().dialogue?.id).toBe(7)
  })
  it('retry preserva texto, chave e posição e bloqueia uma entrada diferente', async () => {
    const { engine, transport, dialogue } = setup()
    await engine.open(31, 'guided', null)
    transport.text.mockRejectedValueOnce(new Error('network'))
    await engine.sendText('Original')
    expect(engine.snapshot().pendingInput).toBe(true)
    await engine.sendText('Different')
    expect(transport.text).toHaveBeenCalledTimes(1)
    dialogue.turns = [turnFixture()]; dialogue.turns_remaining = 11
    await engine.retry()
    expect(transport.text.mock.calls[0]?.slice(0, 3)).toEqual(transport.text.mock.calls[1]?.slice(0, 3))
    expect(engine.snapshot().phase).toBe('idle')
    expect(engine.snapshot().pendingInput).toBe(false)
  })
  it('polling lê a conversa até o turno completar e não reenvia', async () => {
    vi.useFakeTimers()
    const { engine, transport, dialogue } = setup()
    await engine.open(31, 'guided', null)
    dialogue.turns = [{ ...turnFixture(), state: 'pending' }]
    await engine.sendText('I take the bus.')
    expect(engine.snapshot().phase).toBe('waiting')
    dialogue.turns = [turnFixture()]
    await vi.advanceTimersByTimeAsync(10)
    expect(engine.snapshot().phase).toBe('idle')
    expect(transport.text).toHaveBeenCalledTimes(1)
    expect(transport.read).toHaveBeenCalledTimes(2)
    engine.dispose()
  })
  it('retoma apenas a consulta quando o aceite foi confirmado e o GET falhou', async () => {
    const { engine, transport, dialogue } = setup()
    await engine.open(31, 'guided', null)
    transport.read.mockRejectedValueOnce(new Error('network'))
    await engine.sendText('Confirmed input')
    await engine.sendText('Do not send')
    expect(engine.snapshot().awaiting).toBe(true)
    dialogue.turns = [turnFixture()]
    await engine.retry()
    expect(transport.text).toHaveBeenCalledTimes(1)
    expect(engine.snapshot().awaiting).toBe(false)
  })
  it('cota recusada permite abrir nova conversa no Roteiro sem apagar a anterior', async () => {
    const { engine, transport } = setup()
    await engine.open(31, 'guided', null)
    transport.text.mockRejectedValueOnce(new DialogueError(429))
    await engine.sendText('No quota')
    expect(engine.snapshot().message).toContain('Limite')
    engine.leave()
    await engine.open(31, 'script', null)
    expect(transport.remove).not.toHaveBeenCalled()
    expect(transport.create).toHaveBeenLastCalledWith(expect.objectContaining({ mode: 'script' }) as unknown, expect.any(AbortSignal) as unknown)
  })
  it('limite de turnos não admite um envio extra', async () => {
    const { engine, transport, dialogue } = setup()
    dialogue.turns_remaining = 0
    await engine.open(31, 'script', null)
    await engine.sendText('One more')
    expect(transport.text).not.toHaveBeenCalled()
  })
  it('consentimento, bytes, duração e MIME são conferidos antes do upload', async () => {
    const { engine, transport } = setup()
    await engine.open(31, 'guided', null)
    const blob = new Blob(['audio'], { type: 'audio/webm' })
    await engine.sendAudio(blob, 1000, false, policyFixture)
    await engine.sendAudio(blob, 31_000, true, policyFixture)
    await engine.sendAudio(new Blob(['x'], { type: 'text/plain' }), 1000, true, policyFixture)
    await engine.sendAudio(blob, 1000, true, { ...policyFixture, max_bytes: 1 })
    expect(transport.audio).not.toHaveBeenCalled()
    await engine.sendAudio(blob, 1000, true, policyFixture)
    expect(transport.audio).toHaveBeenCalledTimes(1)
  })
  it('não envia áudio no Roteiro', async () => {
    const { engine, transport, dialogue } = setup()
    dialogue.mode = 'script'
    await engine.open(31, 'script', null)
    await engine.sendAudio(new Blob(['x'], { type: 'audio/webm' }), 1000, true, policyFixture)
    expect(transport.audio).not.toHaveBeenCalled()
  })
  it('troca de conta ignora resposta tardia e não inicia polling', async () => {
    const { engine, transport, account } = setup()
    await engine.open(31, 'guided', null)
    let finish!: (value: object) => void
    transport.text.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve }))
    const sending = engine.sendText('Private input')
    account.usuarioId = 4; account.geracao++
    finish({}); await sending
    expect(transport.read).not.toHaveBeenCalled()
    expect(engine.snapshot().message).toContain('sessão mudou')
    await engine.retry()
    expect(transport.text).toHaveBeenCalledTimes(1)
  })
  it('dispose cancela polling e a requisição em voo', async () => {
    vi.useFakeTimers()
    const { engine, transport, dialogue } = setup()
    await engine.open(31, 'guided', null)
    dialogue.turns = [{ ...turnFixture(), state: 'pending' }]
    await engine.sendText('Pending')
    engine.dispose()
    await vi.advanceTimersByTimeAsync(100)
    expect(transport.read).toHaveBeenCalledTimes(1)
  })
  it('falha terminal e fallback encerram a espera', async () => {
    const { engine, dialogue } = setup()
    await engine.open(31, 'guided', null)
    dialogue.turns = [{ ...turnFixture(), state: 'failed', error_code: 'provider_unavailable' }]
    await engine.sendText('Hello')
    expect(engine.snapshot().awaiting).toBe(false)
    dialogue.turns = [{ ...turnFixture(), fallback: true }]
    await engine.refresh()
    expect(engine.snapshot().dialogue?.turns[0]?.fallback).toBe(true)
    engine.dispose()
  })
})
