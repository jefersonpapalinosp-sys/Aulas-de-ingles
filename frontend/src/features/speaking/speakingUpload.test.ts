import { afterEach, describe, expect, it, vi } from 'vitest'
import { hasVoiceDraft } from './voiceDraft'
import { SpeakingUpload, type SpeakingSession, type SpeakingUploadTransport } from './speakingUpload'

const PEDIDO = () => ({
  key: '7:voa-level-1:31:12',
  cueId: 12,
  blob: new Blob(['audio'], { type: 'audio/webm' }),
  duration: 4200,
  rating: 'almost' as const,
})

function conta(overrides: Partial<SpeakingSession> = {}) {
  let session: SpeakingSession = { usuarioId: 7, token: 'tok', perfilNaoConfirmado: false, geracao: 1, ...overrides }
  const createAttempt = vi.fn(async () => ({ id: 55 }))
  const putAudio = vi.fn(async () => ({ ok: true, status: 204 }))
  const transport: SpeakingUploadTransport = { createAttempt, putAudio, session: () => session }
  return { ...transport, createAttempt, putAudio,
    trocar: (patch: Partial<SpeakingSession>) => { session = { ...session, ...patch } } }
}

afterEach(() => { vi.restoreAllMocks() })

describe('SpeakingUpload', () => {
  it('cria a tentativa e manda o áudio, nesta ordem', async () => {
    const transporte = conta()
    const motor = new SpeakingUpload(7, transporte)
    const resultado = await motor.save(PEDIDO())

    expect(transporte.createAttempt).toHaveBeenCalledTimes(1)
    expect(transporte.putAudio).toHaveBeenCalledWith(55, expect.any(Blob), expect.any(AbortSignal))
    expect(resultado).toMatchObject({ ok: true })
    expect(motor.snapshot()).toMatchObject({ saved: true, saving: false, pending: true })
    // Confirmado: a gravação não precisa mais ficar guardada nesta aba.
    expect(hasVoiceDraft(7)).toBe(false)
  })

  it('resposta perdida no áudio não cria uma segunda tentativa no reenvio', async () => {
    const transporte = conta()
    transporte.putAudio.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    const motor = new SpeakingUpload(7, transporte)
    const falha = await motor.save(PEDIDO())
    expect(falha.ok).toBe(false)
    expect(falha.message).toContain('O áudio continua nesta tela')
    expect(motor.snapshot()).toMatchObject({ saving: false, pending: true })

    const reenvio = await motor.save(PEDIDO())
    expect(reenvio.ok).toBe(true)
    // A tentativa já existia: criar outra duplicaria o histórico do aluno.
    expect(transporte.createAttempt).toHaveBeenCalledTimes(1)
    expect(transporte.putAudio).toHaveBeenCalledTimes(2)
  })

  it('recusa do servidor vira a mensagem do status, sem apagar a gravação', async () => {
    const transporte = conta()
    transporte.putAudio.mockResolvedValueOnce({ ok: false, status: 413 })
    const motor = new SpeakingUpload(7, transporte)
    const resultado = await motor.save(PEDIDO())
    expect(resultado.message).toContain('Áudio maior que o limite permitido')
    expect(motor.snapshot().saved).toBe(false)
  })

  it('sessão de outra conta não envia nada', async () => {
    const transporte = conta({ usuarioId: 9 })
    const motor = new SpeakingUpload(7, transporte)
    const resultado = await motor.save(PEDIDO())
    expect(transporte.createAttempt).not.toHaveBeenCalled()
    expect(resultado.message).toContain('Confirme a sessão da mesma conta')
  })

  it('troca de sessão no meio do envio interrompe antes do áudio', async () => {
    const transporte = conta()
    transporte.createAttempt.mockImplementationOnce(async () => {
      transporte.trocar({ geracao: 2 })
      return { id: 55 }
    })
    const motor = new SpeakingUpload(7, transporte)
    const resultado = await motor.save(PEDIDO())
    expect(transporte.putAudio).not.toHaveBeenCalled()
    expect(resultado.message).toContain('A sessão mudou')
  })

  it('sessão perdida preserva a gravação para a volta do aluno', async () => {
    const transporte = conta()
    transporte.createAttempt.mockImplementationOnce(async () => {
      transporte.trocar({ usuarioId: null, token: null })
      return { id: 55 }
    })
    const motor = new SpeakingUpload(7, transporte)
    await motor.save(PEDIDO())
    // Cinco minutos para entrar na mesma conta e voltar ao trecho.
    expect(hasVoiceDraft(7)).toBe(true)
    const recuperada = motor.recover(PEDIDO().key)
    // `pending` porque a tentativa já existe na conta: o reenvio só manda o
    // áudio, sem criar outra.
    expect(recuperada).toMatchObject({ duration: 4200, pending: true })
  })

  it('a gravação recuperada sobrevive a um segundo pedido do mesmo efeito', () => {
    const transporte = conta()
    const motor = new SpeakingUpload(7, transporte)
    const chave = PEDIDO().key
    // Simula o StrictMode: o efeito pede a recuperação duas vezes.
    void motor.save(PEDIDO())
    motor.reset()
    const primeira = motor.recover(chave)
    const segunda = motor.recover(chave)
    expect(primeira).not.toBeNull()
    expect(segunda).toMatchObject({ duration: 4200 })
  })

  it('falha com a sessão viva libera a memória da aba: o áudio está na tela', async () => {
    const transporte = conta()
    transporte.putAudio.mockResolvedValueOnce({ ok: false, status: 422 })
    const motor = new SpeakingUpload(7, transporte)
    await motor.save(PEDIDO())
    // A guarda existe para travessia de sessão, não para falha comum: aqui o
    // blob continua no estado da tela, com o botão de baixar ao lado.
    expect(hasVoiceDraft(7)).toBe(false)
  })

  it('descarte explícito tira a gravação da memória da aba', async () => {
    const transporte = conta()
    transporte.putAudio.mockImplementationOnce(async () => {
      transporte.trocar({ usuarioId: null, token: null })
      throw new TypeError('Failed to fetch')
    })
    const motor = new SpeakingUpload(7, transporte)
    await motor.save(PEDIDO())
    expect(hasVoiceDraft(7)).toBe(true)
    motor.discard(PEDIDO().key)
    expect(hasVoiceDraft(7)).toBe(false)
    expect(motor.recover(PEDIDO().key)).toBeNull()
    expect(motor.snapshot()).toMatchObject({ saving: false, saved: false, pending: false })
  })

  it('dois cliques no mesmo envio não viram dois envios', async () => {
    const transporte = conta()
    let liberar!: () => void
    transporte.putAudio.mockReturnValueOnce(new Promise((done) => { liberar = () => done({ ok: true, status: 204 }) }))
    const motor = new SpeakingUpload(7, transporte)
    const primeiro = motor.save(PEDIDO())
    const segundo = await motor.save(PEDIDO())
    expect(segundo).toMatchObject({ ok: false, message: '' })
    liberar()
    expect((await primeiro).ok).toBe(true)
    expect(transporte.createAttempt).toHaveBeenCalledTimes(1)
  })

  it('troca de frase aborta o envio em voo e nada é dito ao aluno', async () => {
    const transporte = conta()
    let liberar!: () => void
    transporte.putAudio.mockReturnValueOnce(new Promise((done) => { liberar = () => done({ ok: true, status: 204 }) }))
    const motor = new SpeakingUpload(7, transporte)
    const enviando = motor.save(PEDIDO())
    motor.reset()
    liberar()
    expect(await enviando).toMatchObject({ ok: false, message: '' })
    expect(motor.snapshot().saved).toBe(false)
  })
})
