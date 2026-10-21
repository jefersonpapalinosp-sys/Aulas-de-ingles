import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/errors'
import { Erro } from './States'

afterEach(() => vi.restoreAllMocks())

describe('mensagens de recuperação', () => {
  it.each([404, 401, 403, 409, 428, 429, 500, 503])('HTTP %i orienta o aluno e oferece request-id opcional', async (status) => {
    const retry = vi.fn()
    render(<Erro erro={new ApiError('a aula 31', new Response(null, { status, headers: { 'x-request-id': 'req-123' } }))} aoTentarDeNovo={retry} />)
    expect(screen.queryByText(/make up|localhost:8010/)).not.toBeInTheDocument()
    expect(screen.getByText(`HTTP ${status}`)).not.toBeVisible()
    await userEvent.click(screen.getByText('Detalhes técnicos'))
    expect(screen.getByText('req-123')).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Tentar de novo' }))
    expect(retry).toHaveBeenCalledOnce()
    if (status === 404) expect(screen.getByText('Este conteúdo não está disponível.')).toBeVisible()
    if (status === 429) expect(screen.getByText(/muitas solicitações/)).toBeVisible()
    if (status === 409) expect(screen.getByText(/Preserve sua resposta/)).toBeVisible()
    if (status === 428) {
      expect(screen.getByText(/precisa ser atualizada/)).toBeVisible()
      expect(screen.getByText(/Rascunhos e fila local foram preservados/)).toBeVisible()
    }
    if (status === 503) expect(screen.getByText(/temporariamente indisponível/)).toBeVisible()
  })

  it('o código revision_required do cabeçalho orienta a atualização mesmo sem o status', () => {
    const error = new ApiError('o rascunho', new Response(null, { status: 400, headers: { 'x-error-code': 'revision_required' } }))
    expect(error.code).toBe('revision_required')
    render(<Erro erro={error} aoTentarDeNovo={vi.fn()} />)
    expect(screen.getByText(/precisa ser atualizada/)).toBeVisible()
  })
  it('offline não sugere comandos de servidor nem expõe erro arbitrário', () => {
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
    render(<Erro erro={new Error('token=privado')} aoTentarDeNovo={vi.fn()} />)
    expect(screen.getByText('Você está sem conexão.')).toBeInTheDocument()
    expect(screen.queryByText(/privado/)).not.toBeInTheDocument()
  })
  it('identificador inválido não é exposto', () => {
    const error = new ApiError('aula', new Response(null, { status: 500, headers: { 'x-request-id': '<private data>' } }))
    expect(error.requestId).toBeUndefined()
  })
})
