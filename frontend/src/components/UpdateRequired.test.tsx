import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { markRevisionRequired, resetRevisionRequired } from '../api/revisionRequired'
import { UpdateRequired } from './UpdateRequired'

afterEach(() => { act(() => resetRevisionRequired()); localStorage.clear() })

describe('aviso "Atualize o aplicativo" após 428', () => {
  it('não aparece enquanto a API aceita as escritas', () => {
    render(<UpdateRequired />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('aparece ao receber 428 sem roubar o foco, recarrega só após confirmação e preserva rascunho e fila', async () => {
    localStorage.setItem('aulas-ingles:writing-draft:v1:7:4', 'meu texto')
    localStorage.setItem('aulas-ingles:activity-event:v1:7:abc', '{"duration_ms":15000}')
    const reload = vi.fn()
    render(<>
      <textarea aria-label="Seu texto em inglês" defaultValue="digitando" />
      <UpdateRequired reload={reload} />
    </>)
    const editor = screen.getByRole('textbox', { name: 'Seu texto em inglês' })
    editor.focus()

    act(() => markRevisionRequired())
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Atualize o aplicativo.')
    expect(alert).toHaveTextContent(/fila de respostas foram preservados/)
    expect(editor).toHaveFocus()

    await userEvent.click(screen.getByRole('button', { name: 'Recarregar aplicativo…' }))
    expect(reload).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(reload).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Recarregar aplicativo…' }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirmar recarga' }))
    expect(reload).toHaveBeenCalledOnce()
    expect(localStorage.getItem('aulas-ingles:writing-draft:v1:7:4')).toBe('meu texto')
    expect(localStorage.getItem('aulas-ingles:activity-event:v1:7:abc')).toContain('15000')
  })

  it('um segundo 428 não duplica o aviso', async () => {
    render(<UpdateRequired reload={vi.fn()} />)
    act(() => { markRevisionRequired(); markRevisionRequired() })
    expect(await screen.findAllByRole('alert')).toHaveLength(1)
  })
})
