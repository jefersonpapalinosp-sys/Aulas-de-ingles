import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PwaStatus } from './PwaStatus'
import { inspectCache } from './pwa'

vi.mock('./pwa', () => ({
  inspectCache: vi.fn(), registrationError: false, PWA_EVENT: 'aulas:pwa',
}))
const snapshot = { version: 'abc', count: 3, bytes: 3072, lesson: true,
  expiresAt: Date.now() + 86400000, cacheUnavailable: false }
const update = vi.fn()
const getRegistration = vi.fn()
beforeEach(() => {
  vi.mocked(inspectCache).mockResolvedValue(snapshot)
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
    expect(screen.getByText(/Áudio e vídeo continuam online/)).toBeInTheDocument()
  })
  it('mostra espera segura, sem recarregar nem forçar nova versão', async () => {
    getRegistration.mockResolvedValue({ waiting: {}, update })
    show()
    expect(await screen.findByRole('status')).toHaveTextContent('feche todas as abas')
    expect(screen.queryByRole('button', { name: /recarregar/i })).not.toBeInTheDocument()
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
