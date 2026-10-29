import { afterEach, describe, expect, it, vi } from 'vitest'
import { PracticePosition, practicePositionKey } from './practicePosition'
import type { PracticeSession } from './types'

const KEY = practicePositionKey(7, 71)

function sessao(overrides: Partial<PracticeSession> = {}): PracticeSession {
  return {
    id: 71, status: 'active', current_position: 0, state_revision: 3, content_changed: false,
    items: [0, 1, 2].map((position) => ({ position })),
    ...overrides,
  } as unknown as PracticeSession
}

/** Conta em miniatura: o PUT só é aceito com a revisão corrente. */
function conta(session = sessao()) {
  let remote = session
  const save = vi.fn((command: { currentPosition: number; expectedRevision: number; idempotencyKey: string }) => {
    if (command.expectedRevision !== remote.state_revision) return Promise.reject(new Error('revision_conflict'))
    remote = { ...remote, current_position: command.currentPosition, state_revision: remote.state_revision + 1 }
    return Promise.resolve()
  })
  const reload = vi.fn(() => Promise.resolve(remote))
  return { save, reload, remote: () => remote, elsewhere: (patch: Partial<PracticeSession>) => {
    remote = { ...remote, ...patch, state_revision: remote.state_revision + 1 }
  } }
}

afterEach(() => { vi.restoreAllMocks(); localStorage.clear() })

describe('PracticePosition', () => {
  it('espelha antes da rede e limpa o espelho quando a conta confirma', async () => {
    const transporte = conta()
    const motor = new PracticePosition(7, transporte)
    await motor.moveTo(sessao(), 1, true)
    expect(transporte.save).toHaveBeenCalledWith({ sessionId: 71, currentPosition: 1, expectedRevision: 3,
      idempotencyKey: expect.any(String) as unknown })
    expect(motor.snapshot().local).toBeNull()
    expect(localStorage.getItem(KEY)).toBeNull()
    expect(transporte.remote().current_position).toBe(1)
  })

  it('offline guarda a posição no dispositivo e não chama a conta', async () => {
    const transporte = conta()
    const motor = new PracticePosition(7, transporte)
    await motor.moveTo(sessao(), 2, false)
    expect(transporte.save).not.toHaveBeenCalled()
    expect(motor.snapshot().local).toBe(2)
    expect(localStorage.getItem(KEY)).toBe('2')
  })

  it('revisão concorrente é reenviada com a MESMA chave de idempotência', async () => {
    const transporte = conta()
    const motor = new PracticePosition(7, transporte)
    // Outra aba avançou a revisão entre a leitura e o envio.
    transporte.elsewhere({})
    await motor.moveTo(sessao(), 1, true)

    expect(transporte.save).toHaveBeenCalledTimes(2)
    const [primeira, segunda] = transporte.save.mock.calls.map(([command]) => command)
    expect(primeira!.expectedRevision).toBe(3)
    expect(segunda!.expectedRevision).toBe(4)
    // A chave repetida é o que distingue "revisão nova" de "cobrar duas vezes".
    expect(segunda!.idempotencyKey).toBe(primeira!.idempotencyKey)
    expect(motor.snapshot().local).toBeNull()
  })

  it('resposta perdida depois de aplicada não reenvia: a conta já está na posição', async () => {
    const transporte = conta()
    transporte.save.mockImplementationOnce(() => {
      transporte.elsewhere({ current_position: 1 })
      return Promise.reject(new TypeError('network'))
    })
    const motor = new PracticePosition(7, transporte)
    await motor.moveTo(sessao(), 1, true)
    expect(transporte.save).toHaveBeenCalledTimes(1)
    expect(motor.snapshot()).toMatchObject({ local: null, error: '' })
  })

  it('conteúdo trocado não recebe posição nova e o espelho é preservado', async () => {
    const transporte = conta()
    transporte.save.mockRejectedValueOnce(new Error('conflict'))
    transporte.reload.mockResolvedValueOnce(sessao({ content_changed: true, state_revision: 9 }))
    const motor = new PracticePosition(7, transporte)
    await motor.moveTo(sessao(), 2, true)

    expect(transporte.save).toHaveBeenCalledTimes(1)
    expect(motor.snapshot().error).toContain('Posição não sincronizada')
    // O espelho fica: é o único lugar onde a posição do aluno existe.
    expect(localStorage.getItem(KEY)).toBe('2')
  })

  it('posição que o pack não tem mais é descartada na leitura', () => {
    localStorage.setItem(KEY, '7')
    const motor = new PracticePosition(7, conta())
    motor.load(sessao())
    expect(motor.snapshot().local).toBeNull()
  })

  it('espelho igual à conta é esquecido sem tocar a rede', async () => {
    localStorage.setItem(KEY, '1')
    const transporte = conta()
    const motor = new PracticePosition(7, transporte)
    const session = sessao({ current_position: 1 })
    motor.load(session)
    expect(motor.snapshot().local).toBe(1)
    await motor.settle(session, true)
    expect(transporte.save).not.toHaveBeenCalled()
    expect(localStorage.getItem(KEY)).toBeNull()
  })

  it('armazenamento recusado não impede navegar, mas avisa', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('', 'QuotaExceededError') })
    const transporte = conta()
    const motor = new PracticePosition(7, transporte)
    await motor.moveTo(sessao(), 1, false)
    expect(motor.snapshot().local).toBe(1)
    expect(motor.snapshot().storageWarning).toContain('apenas nesta tela')
  })

  it('confirmação em voo não apaga a posição mais nova do aluno', async () => {
    const transporte = conta()
    let liberar!: () => void
    transporte.save.mockReturnValueOnce(new Promise<void>((done) => { liberar = () => done() }))
    const motor = new PracticePosition(7, transporte)
    const navegando = motor.moveTo(sessao(), 1, true)
    // O aluno avança antes da resposta; a sincronização em voo não é cancelada.
    await motor.moveTo(sessao(), 2, true)
    liberar()
    await navegando

    // A confirmação era da posição 1; o espelho guarda a 2 e precisa sobreviver.
    expect(localStorage.getItem(KEY)).toBe('2')
    expect(motor.snapshot().local).toBe(2)
  })

  it('descarte para de publicar para uma tela que já saiu', async () => {
    const motor = new PracticePosition(7, conta())
    const ouvinte = vi.fn()
    motor.subscribe(ouvinte)
    motor.dispose()
    await motor.moveTo(sessao(), 1, true)
    expect(ouvinte).not.toHaveBeenCalled()
  })
})
