import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PwaStatus } from './PwaStatus'
import { updateAppAndReload } from './appUpdate'
import { inspectCache } from './pwa'

vi.mock('./appUpdate', () => ({ updateAppAndReload: vi.fn() }))
vi.mock('./pwa', () => ({
  inspectCache: vi.fn(), registrationError: false, PWA_EVENT: 'aulas:pwa',
}))
const snapshot = { version: 'abc', count: 3, bytes: 3072, lesson: true,
  expiresAt: Date.now() + 86400000, cacheUnavailable: false }
const update = vi.fn()
const getRegistration = vi.fn()
beforeEach(() => {
  vi.mocked(inspectCache).mockResolvedValue(snapshot)
  vi.mocked(updateAppAndReload).mockResolvedValue()
  getRegistration.mockResolvedValue({ waiting: null, update })
  Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: { getRegistration } })
})
afterEach(() => { vi.restoreAllMocks(); vi.clearAllMocks() })
const show = () => render(<MemoryRouter initialEntries={['/cursos/voa-level-1/aulas/31']}><PwaStatus /></MemoryRouter>)

describe('disponibilidade offline', () => {
  it('mostra somente a disponibilidade comprovada e distingue áudio/gravações', async () => {
    show()
    fireEvent.click(screen.getByText('Offline e atualizações'))
    expect(await screen.findByText(/Texto desta aula armazenado até/)).toBeInTheDocument()
    expect(inspectCache).toHaveBeenCalledWith('PWA_STATUS', '/api/courses/voa-level-1/lessons/31')
    expect(screen.getByText(/Áudio, vídeo e gravações exigem rede/)).toBeInTheDocument()
  })
  it('oferece ativação confirmada quando uma nova versão está aguardando', async () => {
    getRegistration.mockResolvedValue({ waiting: {}, update })
    show()
    expect(await screen.findByRole('status')).toHaveTextContent('só então recarrega')
    expect(screen.getByRole('button', { name: 'Recarregar aplicativo…' })).toBeInTheDocument()
  })
  it('mantém a ativação montada quando controllerchange remove o waiting', async () => {
    let waiting: object | null = {}
    let signal: AbortSignal | undefined
    let finish: (() => void) | undefined
    getRegistration.mockImplementation(() => Promise.resolve({ waiting, update }))
    vi.mocked(updateAppAndReload).mockImplementation((options) => {
      signal = options?.signal
      return new Promise<void>((resolve) => { finish = resolve })
    })
    show()
    fireEvent.click(await screen.findByRole('button', { name: 'Recarregar aplicativo…' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar recarga' }))
    await waitFor(() => expect(updateAppAndReload).toHaveBeenCalledOnce())
    waiting = null
    window.dispatchEvent(new Event('aulas:pwa'))
    await waitFor(() => expect(getRegistration).toHaveBeenCalledTimes(2))
    expect(signal?.aborted).toBe(false)
    expect(screen.getByRole('button', { name: 'Atualizando…' })).toBeInTheDocument()
    finish?.()
  })
  it('exige confirmação e remove somente texto público', async () => {
    show()
    fireEvent.click(screen.getByText('Offline e atualizações'))
    const button = screen.getByRole('button', { name: 'Limpar somente textos públicos' })
    await waitFor(() => expect(button).toBeEnabled())
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    fireEvent.click(button)
    expect(inspectCache).not.toHaveBeenCalledWith('PWA_CLEAR_TEXT', expect.anything())
    confirm.mockReturnValue(true)
    fireEvent.click(button)
    expect(await screen.findByText(/Textos removidos/)).toBeInTheDocument()
    expect(inspectCache).toHaveBeenCalledWith('PWA_CLEAR_TEXT', '/api/courses/voa-level-1/lessons/31')
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('não serão apagados') as unknown)
  })
  it('não promete offline quando armazenamento ou worker falham', async () => {
    vi.mocked(inspectCache).mockRejectedValue(new Error('QuotaExceededError'))
    show()
    fireEvent.click(screen.getByText('Offline e atualizações'))
    expect(await screen.findByText(/Disponibilidade offline não confirmada/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Limpar somente textos públicos' })).toBeDisabled()
  })
})
