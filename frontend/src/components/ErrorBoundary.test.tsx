import { lazy, Suspense } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ErrorBoundary, RecoveryScreen } from './ErrorBoundary'

beforeEach(() => { vi.spyOn(console, 'error').mockImplementation(() => undefined) })
afterEach(() => { vi.restoreAllMocks(); localStorage.clear() })

function Broken(): never { throw new Error('segredo que não deve ser mostrado') }

describe('recuperação de renderização e chunks', () => {
  it('mantém shell, dá foco à recuperação e não limpa rascunhos', async () => {
    localStorage.setItem('draft', 'meu texto')
    render(<><nav>Trilha</nav><ErrorBoundary><Broken /></ErrorBoundary></>)
    expect(screen.getByRole('navigation')).toHaveTextContent('Trilha')
    expect(screen.getByRole('heading', { name: 'Esta área encontrou um problema' })).toHaveFocus()
    expect(screen.queryByText(/segredo/)).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Tentar abrir novamente' }))
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(localStorage.getItem('draft')).toBe('meu texto')
  })
  it('trocar rota recupera a área sem depender de reload', () => {
    const view = render(<ErrorBoundary resetKey="aula"><Broken /></ErrorBoundary>)
    view.rerender(<ErrorBoundary resetKey="inicio"><h1>Hoje</h1></ErrorBoundary>)
    expect(screen.getByRole('heading', { name: 'Hoje' })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
  it('rejeição de import lazy usa mensagem específica, não retry impossível de React.lazy', async () => {
    const Page = lazy(() => { return Promise.reject(new TypeError('Failed to fetch dynamically imported module')) })
    render(<ErrorBoundary><Suspense fallback="Carregando"><Page /></Suspense></ErrorBoundary>)
    expect(await screen.findByRole('heading', { name: 'Não foi possível carregar esta tela' })).toHaveFocus()
    expect(screen.queryByRole('button', { name: 'Tentar abrir novamente' })).not.toBeInTheDocument()
  })
  it('recarrega somente após confirmação explícita; cancelar não faz nada', async () => {
    const reload = vi.fn()
    render(<RecoveryScreen chunk onRetry={vi.fn()} reload={reload} />)
    expect(reload).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Recarregar aplicativo…' }))
    expect(reload).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(reload).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Recarregar aplicativo…' }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirmar recarga' }))
    expect(reload).toHaveBeenCalledOnce()
  })
})
