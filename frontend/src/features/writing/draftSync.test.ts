import { afterEach, describe, expect, it, vi } from 'vitest'
import type { WritingDraft } from '../../api/client'
import { DRAFT_SAVE_DELAY, DraftConflict, DraftSync } from './draftSync'

const KEY = 'aulas-ingles:writing-draft:v1:7:4'

/** Conta de verdade em miniatura: a revisão só avança por save aceito. */
function account(initial: Partial<WritingDraft> = {}) {
  let remote: WritingDraft = { prompt_id: 4, text: '', revision: 0, updated_at: null, ...initial }
  const read = vi.fn(async () => remote)
  const save = vi.fn(async (body: { text: string; expected_revision: number }) => {
    if (body.expected_revision !== remote.revision) throw new DraftConflict(remote)
    remote = { ...remote, text: body.text, revision: (remote.revision ?? 0) + 1, updated_at: new Date().toISOString() }
    return remote
  })
  const createVersion = vi.fn(async (body: { text: string; expected_revision: number }) => {
    if (body.expected_revision !== remote.revision) throw new DraftConflict(remote)
    remote = { ...remote, revision: (remote.revision ?? 0) + 1 }
    return { id: 1, version: 1, text: body.text, created_at: new Date().toISOString(), draft_revision: remote.revision }
  })
  return { read, save, createVersion, remote: () => remote,
    elsewhere: (text: string) => { remote = { ...remote, text, revision: (remote.revision ?? 0) + 1, updated_at: new Date().toISOString() } } }
}

const settle = () => new Promise((done) => setTimeout(done, DRAFT_SAVE_DELAY + 50))

afterEach(() => { vi.restoreAllMocks(); localStorage.clear() })

describe('DraftSync', () => {
  it('resposta que chega depois do descarte não apaga espelho mais novo', async () => {
    const conta = account({ text: 'Old.' })
    let liberar!: (draft: WritingDraft) => void
    conta.save.mockReturnValue(new Promise((done) => { liberar = done }))
    const sync = new DraftSync(7, 4, conta)
    await sync.hydrate()
    sync.change('Pendente.')
    await settle()
    expect(conta.save).toHaveBeenCalledTimes(1)

    sync.dispose()
    localStorage.setItem(KEY, 'Mais novo.')
    liberar({ prompt_id: 4, text: 'Pendente.', revision: 1, updated_at: null })
    await settle()

    // O texto desta tela não é mais o da fila; apagar o espelho perderia o novo.
    expect(localStorage.getItem(KEY)).toBe('Mais novo.')
  })

  it('espelho divergente da conta vira conflito, e nada é salvo antes da escolha', async () => {
    localStorage.setItem(KEY, 'Meu texto.')
    const conta = account({ text: 'Da conta.', revision: 8, updated_at: '2026-10-14T03:00:00Z' })
    const sync = new DraftSync(7, 4, conta)
    await sync.hydrate()

    // Espelho sem revisão de origem: pode ter nascido de qualquer revisão.
    expect(sync.snapshot()).toMatchObject({ text: 'Meu texto.', recovered: true, conflict: { text: 'Da conta.' } })
    sync.change('Continuo editando.')
    await settle()
    expect(conta.save).not.toHaveBeenCalled()

    sync.resolve(false)
    await settle()
    expect(conta.save).toHaveBeenCalledWith({ text: 'Continuo editando.', expected_revision: 8 })
    expect(sync.snapshot()).toMatchObject({ conflict: null, status: 'saved' })
    expect(localStorage.getItem(KEY)).toBeNull()
  })

  it('escolher a conta troca o texto e some com o espelho, sem salvar', async () => {
    localStorage.setItem(KEY, 'Meu texto.')
    const conta = account({ text: 'Da conta.', revision: 8, updated_at: '2026-10-14T03:00:00Z' })
    const sync = new DraftSync(7, 4, conta)
    await sync.hydrate()
    sync.resolve(true)
    expect(sync.snapshot()).toMatchObject({ text: 'Da conta.', conflict: null, revision: 8 })
    expect(localStorage.getItem(KEY)).toBeNull()
    expect(conta.save).not.toHaveBeenCalled()
  })

  it('conflito vindo do save preserva os dois textos e espera a escolha', async () => {
    const conta = account({ text: 'Original.', revision: 1 })
    const sync = new DraftSync(7, 4, conta)
    await sync.hydrate()
    conta.elsewhere('Outro dispositivo.')
    sync.change('Meu texto.')
    await settle()

    expect(conta.save).toHaveBeenCalledTimes(1)
    expect(sync.snapshot()).toMatchObject({ text: 'Meu texto.', conflict: { text: 'Outro dispositivo.' } })
    // O texto do aluno continua na tela e no dispositivo.
    expect(localStorage.getItem(KEY)).toBe('Meu texto.')

    sync.resolve(false)
    await settle()
    expect(conta.save).toHaveBeenLastCalledWith({ text: 'Meu texto.', expected_revision: 2 })
    expect(conta.remote().text).toBe('Meu texto.')
  })

  it('falha de rede não afirma persistência, e o espelho decide a mensagem', async () => {
    const conta = account()
    conta.save.mockRejectedValue(new TypeError('offline'))
    const sync = new DraftSync(7, 4, conta)
    await sync.hydrate()
    sync.change('Fica nesta tela.')
    await settle()
    // Com espelho local: pendente de sincronização.
    expect(sync.snapshot().status).toBe('local')
    expect(localStorage.getItem(KEY)).toBe('Fica nesta tela.')

    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('', 'QuotaExceededError') })
    sync.change('Sem espelho.')
    await settle()
    // Sem espelho: o texto está só na tela, e a mensagem precisa dizer isso.
    expect(sync.snapshot().status).toBe('unsaved')
    expect(sync.snapshot().storageWarning).toContain('Copie o texto antes de sair')
  })

  it('fila serial: dois textos seguidos avançam a revisão em ordem', async () => {
    const conta = account()
    const sync = new DraftSync(7, 4, conta)
    await sync.hydrate()
    sync.change('Primeiro.')
    await settle()
    sync.change('Segundo.')
    await sync.flush()
    expect(conta.save.mock.calls.map(([body]) => body.expected_revision)).toEqual([0, 1])
    expect(conta.remote()).toMatchObject({ text: 'Segundo.', revision: 2 })
  })

  it('versão usa a revisão que o autosave acabou de avançar', async () => {
    const conta = account()
    const sync = new DraftSync(7, 4, conta)
    await sync.hydrate()
    sync.change('Texto da versão.')
    const versao = await sync.createVersion()
    expect(conta.createVersion).toHaveBeenCalledWith({ text: 'Texto da versão.', expected_revision: 1 })
    expect(versao).toMatchObject({ version: 1, draft_revision: 2 })
    expect(sync.snapshot().revision).toBe(2)
  })

  it('sem revisão confirmada, lê a conta antes de escrever sobre ela', async () => {
    const conta = account({ text: 'Da conta.' })
    conta.read.mockRejectedValueOnce(new TypeError('offline'))
    const sync = new DraftSync(7, 4, conta)
    await sync.hydrate()
    // Leitura falhou: não há revisão, e o texto está só nesta tela.
    expect(sync.snapshot()).toMatchObject({ revision: null, status: 'unsaved' })

    sync.change('Meu texto.')
    await settle()
    // A conta tem outro texto: é conflito, não sobrescrita.
    expect(conta.save).not.toHaveBeenCalled()
    expect(sync.snapshot().conflict).toMatchObject({ text: 'Da conta.' })
  })

  it('descarte cancela o autosave que ainda não saiu', async () => {
    const conta = account()
    const sync = new DraftSync(7, 4, conta)
    await sync.hydrate()
    sync.change('Nunca sai.')
    sync.dispose()
    await settle()
    expect(conta.save).not.toHaveBeenCalled()
    // Mas o espelho local fica: cancelar o envio não é apagar o texto.
    expect(localStorage.getItem(KEY)).toBe('Nunca sai.')
  })
})
