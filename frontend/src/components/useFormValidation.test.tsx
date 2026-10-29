import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { useFormValidation } from './useFormValidation'

function Form({ label }: { label: string }) {
  const validation = useFormValidation()
  const help = `${validation.id}-help`
  return <form aria-label={label} onSubmit={(event) => event.preventDefault()}>
    <p id={help}>Informe um e-mail e uma meta.</p>
    <label>E-mail<input type="email" required {...validation.field('email', help)} /></label>
    <label>Meta<input required {...validation.field('goal', help)} /></label>
    {validation.messages}
    <button>Salvar</button>
    <button type="button" onClick={validation.reset}>Recomeçar</button>
  </form>
}

describe('validação acessível do formulário', () => {
  it('associa erros nativos aos campos e mantém a ajuda ao corrigir somente um deles', async () => {
    const user = userEvent.setup()
    render(<Form label="Plano" />)
    const email = screen.getByLabelText('E-mail')
    const goal = screen.getByLabelText('Meta')
    expect(email).toHaveAttribute('aria-invalid', 'false')
    await user.click(screen.getByRole('button', { name: 'Salvar' }))
    expect(email).toHaveAttribute('aria-invalid', 'true')
    expect(goal).toHaveAttribute('aria-invalid', 'true')
    for (const field of [email, goal]) {
      const ids = field.getAttribute('aria-describedby')!.split(' ')
      expect(ids).toHaveLength(2)
      expect(document.getElementById(ids[0]!)).toHaveTextContent('Informe um e-mail')
      expect(document.getElementById(ids[1]!)).toHaveAttribute('role', 'alert')
    }
    await user.type(email, 'aluno@example.com')
    expect(email).toHaveAttribute('aria-invalid', 'false')
    expect(email).toHaveAccessibleDescription('Informe um e-mail e uma meta.')
    expect(goal).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getAllByRole('alert')).toHaveLength(1)
    await user.click(screen.getByRole('button', { name: 'Recomeçar' }))
    expect(screen.queryByRole('alert')).toBeNull()
    expect(goal).toHaveAttribute('aria-invalid', 'false')
  })

  it('separa IDs e erros de duas instâncias montadas ao mesmo tempo', () => {
    render(<><Form label="Primeiro" /><Form label="Segundo" /></>)
    const first = within(screen.getByRole('form', { name: 'Primeiro' })).getByLabelText('E-mail')
    const second = within(screen.getByRole('form', { name: 'Segundo' })).getByLabelText('E-mail')
    fireEvent.invalid(first)
    expect(first.getAttribute('aria-describedby')).not.toBe(second.getAttribute('aria-describedby'))
    expect(first).toHaveAttribute('aria-invalid', 'true')
    expect(second).toHaveAttribute('aria-invalid', 'false')
    expect(second).toHaveAccessibleDescription('Informe um e-mail e uma meta.')
  })
})
