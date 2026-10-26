import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PersonalDataPage } from './PersonalDataPage'

const mocks = vi.hoisted(() => ({
  fetch: vi.fn(), cache: vi.fn(), clear: vi.fn(), ended: vi.fn(), offline: false,
}))
vi.mock('../api/auth', () => ({ useSessao: () => ({ usuario: { id: 1 },
  offline: mocks.offline, encerrarContaExcluida: mocks.ended }) }))
vi.mock('../api/client', () => ({ authenticatedFetch: mocks.fetch }))
vi.mock('../features/offline/pwa', () => ({ inspectCache: mocks.cache }))
vi.mock('../features/privacy/deviceInventory', () => ({
  inspectDevice: async () => ({ drafts: 1, mediaCommands: 0, activityEvents: 0,
    localCopies: 0, pendingAnswers: 2, blockedAnswers: 1, voiceDraft: false }),
  clearDeviceData: mocks.clear,
}))
vi.mock('../features/offline/attemptQueue', () => ({
  subscribeAttemptQueue: () => () => undefined,
  getAttemptQueueStats: async () => ({ pending: 2, blocked: 1 }),
}))

const exported = {
  schema_version: '2.1', scope: { snapshot_at: '2026-10-15T10:00:00Z' },
  audio_manifest: [{ attempt_id: 7, mime_type: 'audio/webm', file_size: 1000, sha256: 'a'.repeat(64),
    integrity_state: 'verified', download_path: '/api/speaking/attempts/7/audio' }],
}
const setup = () => render(<MemoryRouter><PersonalDataPage /></MemoryRouter>)

describe('Meus dados', () => {
  beforeEach(() => {
    vi.restoreAllMocks(); mocks.fetch.mockReset(); mocks.cache.mockReset(); mocks.clear.mockReset()
    mocks.ended.mockReset(); localStorage.clear(); mocks.offline = false
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:download'), revokeObjectURL: vi.fn() }))
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
  })
  afterEach(() => { cleanup(); vi.unstubAllGlobals() })

  it('exporta por ação explícita e baixa áudio autenticado sem persistir o JSON', async () => {
    mocks.fetch.mockResolvedValueOnce(new Response(JSON.stringify(exported)))
      .mockResolvedValueOnce(new Response('synthetic audio'))
    setup()
    expect(mocks.fetch).not.toHaveBeenCalled()
    expect(screen.getByText(/Não é um backup restaurável/)).toBeVisible()
    const user = userEvent.setup()
    const download = screen.getByRole('button', { name: 'Baixar meus dados em JSON' })
    download.focus()
    await user.keyboard('{Enter}')
    await screen.findByRole('button', { name: 'Baixar gravação 7' })
    expect(mocks.fetch).toHaveBeenCalledWith('/api/me/export', expect.objectContaining({ cache: 'no-store', signal: expect.any(AbortSignal) }))
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1)
    expect(localStorage.length).toBe(0)
    await user.click(screen.getByRole('button', { name: 'Baixar gravação 7' }))
    await waitFor(() => expect(mocks.fetch).toHaveBeenLastCalledWith('/api/speaking/attempts/7/audio', expect.anything()))
    expect(screen.getByText(/salvamento no dispositivo não pode ser confirmado/)).toBeVisible()
  })

  it('comunica limite e permite tentar novamente sem baixar arquivo parcial', async () => {
    mocks.fetch.mockResolvedValueOnce(new Response('{}', { status: 413 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...exported, audio_manifest: [] })))
    setup()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Baixar meus dados em JSON' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Nenhum arquivo parcial')
    expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Baixar meus dados em JSON' }))
    expect(await screen.findByText(/Nenhuma gravação registrada/)).toBeVisible()
  })

  it('aceita minor novo da linha 2.x e recusa linha futura sem salvar arquivo', async () => {
    mocks.fetch.mockResolvedValueOnce(new Response(JSON.stringify({ ...exported, schema_version: '2.9' })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...exported, schema_version: '3.0' })))
    setup()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Baixar meus dados em JSON' }))
    await screen.findByRole('button', { name: 'Baixar gravação 7' })
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1)
    await user.click(screen.getByRole('button', { name: 'Baixar meus dados em JSON' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Atualize a aplicação')
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1)
  })

  it('informa sessão offline e não tenta exportar', () => {
    mocks.offline = true
    setup()
    expect(screen.getByRole('button', { name: 'Baixar meus dados em JSON' })).toBeDisabled()
    expect(screen.getByText(/Conecte-se e confirme sua sessão/)).toBeVisible()
    expect(mocks.fetch).not.toHaveBeenCalled()
  })

  it('confirma limpeza estritamente pública e preserva todos os dados locais', async () => {
    localStorage.setItem('aulas-ingles:writing-draft:v1:1:3', 'preserve')
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    mocks.cache.mockResolvedValue({ count: 0 })
    setup()
    const user = userEvent.setup()
    const button = screen.getByRole('button', { name: 'Limpar somente textos públicos deste navegador' })
    await user.click(button)
    expect(mocks.cache).not.toHaveBeenCalled()
    confirm.mockReturnValue(true)
    await user.click(button)
    expect(mocks.cache).toHaveBeenCalledExactlyOnceWith('PWA_CLEAR_TEXT')
    expect(localStorage.getItem('aulas-ingles:writing-draft:v1:1:3')).toBe('preserve')
    expect(screen.getByText(/Nenhum dado pessoal ou remoto foi apagado/)).toBeVisible()
  })

  it('falha de cache não vira sucesso nem remove rascunhos', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mocks.cache.mockRejectedValue(new Error('no SW'))
    setup()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Limpar somente textos públicos deste navegador' }))
    expect(await screen.findByText(/Não foi possível confirmar a limpeza/)).toBeVisible()
  })

  it('cancela a leitura ao sair e não dispara download tardio em outra conta', async () => {
    let resolve!: (response: Response) => void
    mocks.fetch.mockImplementation(() => new Promise<Response>((r) => { resolve = r }))
    const view = setup()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Baixar meus dados em JSON' }))
    const signal = mocks.fetch.mock.calls[0]![1].signal as AbortSignal
    view.unmount()
    expect(signal.aborted).toBe(true)
    resolve(new Response(JSON.stringify(exported)))
    await Promise.resolve()
    expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled()
  })

  it('áudio removido após o snapshot comunica falha preservando o manifesto', async () => {
    mocks.fetch.mockResolvedValueOnce(new Response(JSON.stringify(exported)))
      .mockResolvedValueOnce(new Response('{}', { status: 404 }))
    setup()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Baixar meus dados em JSON' }))
    await user.click(await screen.findByRole('button', { name: 'Baixar gravação 7' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Preserve qualquer cópia local')
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1)
  })

  it('limpa dados privados locais somente após confirmação explícita', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)
    mocks.clear.mockResolvedValue(4)
    setup()
    const button = screen.getByRole('button', { name: 'Apagar dados locais desta conta' })
    await userEvent.setup().click(button)
    expect(mocks.clear).not.toHaveBeenCalled()
    await userEvent.setup().click(button)
    expect(confirm).toHaveBeenCalledTimes(2)
    expect(mocks.clear).toHaveBeenCalledExactlyOnceWith(1)
    expect(await screen.findByText(/4 item\(ns\) local\(is\) removido/)).toBeVisible()
  })

  it('exige senha, frase e segunda confirmação para excluir a conta', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mocks.fetch.mockResolvedValue(new Response(JSON.stringify({
      state: 'cleanup_pending', database_deleted: true,
    }), { status: 202, headers: { 'Content-Type': 'application/json' } }))
    setup()
    const user = userEvent.setup()
    const submit = screen.getByRole('button', { name: 'Excluir minha conta definitivamente' })
    expect(submit).toBeDisabled()
    await user.type(screen.getByLabelText('Senha atual'), 'senha-bem-grande')
    await user.type(screen.getByLabelText(/Digite EXCLUIR MINHA CONTA/), 'EXCLUIR MINHA CONTA')
    await user.click(submit)
    await waitFor(() => expect(mocks.ended).toHaveBeenCalledExactlyOnceWith(true))
    const [path, options] = mocks.fetch.mock.calls[0]!
    expect(path).toBe('/api/me/account')
    expect(options).toMatchObject({ method: 'DELETE', cache: 'no-store' })
    expect(JSON.parse(options.body)).toMatchObject({
      password: 'senha-bem-grande', confirmation: 'EXCLUIR MINHA CONTA',
    })
  })

  it('senha incorreta preserva a sessão e informa que nada foi excluído', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mocks.fetch.mockResolvedValue(new Response('{}', { status: 401 }))
    setup()
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Senha atual'), 'senha-incorreta')
    await user.type(screen.getByLabelText(/Digite EXCLUIR MINHA CONTA/), 'EXCLUIR MINHA CONTA')
    await user.click(screen.getByRole('button', { name: 'Excluir minha conta definitivamente' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('A conta não foi excluída')
    expect(mocks.ended).not.toHaveBeenCalled()
  })
})
