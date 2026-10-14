import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ConnectivityStatus } from './ConnectivityStatus'
import { listQueuedAttempts, queueAttempt } from './attemptQueue'
import { attemptStore } from './attemptQueueStore'

function montar() {
  return render(<QueryClientProvider client={new QueryClient()}><MemoryRouter>
    <ConnectivityStatus userId={7} offlineSession />
  </MemoryRouter></QueryClientProvider>)
}

const entry = (n: number, userId = 7) => ({ userId, exerciseId: n, answer: `answer-${n}`,
  idempotencyKey: `id-${n}`, createdAt: '2026-10-13T10:00:00Z', courseSlug: 'voa-level-2', lessonNumber: 6 })

beforeEach(() => {
  localStorage.clear()
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
})
afterEach(() => vi.restoreAllMocks())

describe('painel da fila', () => {
  it('expõe motivo, texto e aula; remoção exige confirmação e não afeta pendentes ou outra conta', async () => {
    await Promise.all([queueAttempt(entry(1)), queueAttempt(entry(2)), queueAttempt(entry(1, 8))])
    await attemptStore.block(7, 'id-1', 409)
    await attemptStore.block(8, 'id-1', 409)
    const user = userEvent.setup()
    const view = montar()
    expect(await screen.findByText(/1 pendente\(s\) · 1 bloqueada/)).toBeInTheDocument()
    await user.click(screen.getByText('Consultar respostas preservadas'))
    expect(screen.getByText(/O conteúdo ou a sessão mudou/)).toBeInTheDocument()
    expect(screen.getByText('answer-1')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Abrir exercícios da aula' })[0]).toHaveAttribute('href', '/cursos/voa-level-2/aulas/6/exercicios')
    await user.click(screen.getByRole('button', { name: 'Descartar incompatíveis…' }))
    expect(await listQueuedAttempts(7)).toHaveLength(2)
    await user.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(await listQueuedAttempts(7)).toHaveLength(2)
    await user.click(screen.getByRole('button', { name: 'Descartar incompatíveis…' }))
    await user.click(screen.getByRole('button', { name: 'Confirmar remoção' }))
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('1 pendente(s) · 0 bloqueada(s).'))
    expect(await screen.findByText(/Respostas selecionadas removidas/)).toBeInTheDocument()
    view.unmount()
    expect(await listQueuedAttempts(7)).toEqual([entry(2)])
    expect(await listQueuedAttempts(8)).toHaveLength(1)
  })

  it('falha de leitura não é apresentada como fila vazia', async () => {
    vi.spyOn(attemptStore, 'list').mockRejectedValue(new Error('Armazenamento bloqueado'))
    montar()
    expect(await screen.findByRole('alert')).toHaveTextContent('Armazenamento bloqueado')
    expect(screen.getByRole('status')).not.toHaveTextContent('0 pendente')
    expect(screen.getByRole('button', { name: 'Consultar fila novamente' })).toBeEnabled()
  })

  it('falha ao remover não anuncia sucesso nem descarta a resposta', async () => {
    await queueAttempt(entry(1))
    await attemptStore.block(7, 'id-1', 422)
    vi.spyOn(attemptStore, 'discardBlocked').mockRejectedValue(new Error('Não foi possível remover'))
    const user = userEvent.setup()
    montar()
    await user.click(await screen.findByRole('button', { name: 'Descartar incompatíveis…' }))
    await user.click(screen.getByRole('button', { name: 'Confirmar remoção' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível remover')
    expect(screen.queryByText(/Respostas selecionadas removidas/)).not.toBeInTheDocument()
    expect(await listQueuedAttempts(7)).toHaveLength(1)
  })
})
