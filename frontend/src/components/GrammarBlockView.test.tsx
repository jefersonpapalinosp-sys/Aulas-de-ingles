import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { GrammarBlock } from '../api/client'
import { GrammarBlockView } from './GrammarBlockView'

const bloco: GrammarBlock = {
  heading: 'Comparativo: a regra decide pelo tamanho do adjetivo',
  why: 'Em inglês você não escolhe entre *-er* e *more* por gosto.',
  warning: '**Erro clássico** Não existe "more faster".',
  table_head: ['Adjetivo', 'Comparativo', 'Frase da aula'],
  rows: [
    { cells: ['fast (1 sílaba)', 'fast**er** than', 'A taxi is **faster than** a bus.'] },
    { cells: ['good (irregular)', 'better than', 'Being early is **better than** being late.'] },
  ],
}

describe('GrammarBlockView', () => {
  it('monta a tabela com cabeçalho e uma linha por regra', () => {
    render(<GrammarBlockView bloco={bloco} />)
    expect(screen.getAllByRole('columnheader')).toHaveLength(3)
    expect(screen.getAllByRole('row')).toHaveLength(3) // cabeçalho + 2
  })

  it('renderiza o Markdown das células como marcação, não como texto', () => {
    const { container } = render(<GrammarBlockView bloco={bloco} />)
    const celula = screen.getAllByRole('cell')[1]!
    expect(celula.querySelector('strong')).toHaveTextContent('er')
    expect(container.textContent).not.toContain('**')
  })

  it('mostra o alerta quando existe', () => {
    render(<GrammarBlockView bloco={bloco} />)
    expect(screen.getByText(/Não existe/)).toBeInTheDocument()
  })

  it('omite a tabela num bloco que não tem', () => {
    render(<GrammarBlockView bloco={{ ...bloco, table_head: null, rows: [] }} />)
    expect(screen.queryByRole('table')).toBeNull()
  })
})
