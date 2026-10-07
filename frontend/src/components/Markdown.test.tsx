import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Markdown } from './Markdown'

describe('Markdown', () => {
  it('converte negrito, itálico, código e riscado', () => {
    const { container } = render(
      <Markdown>{'**forte** e *fraco* e `cod` e ~~fora~~'}</Markdown>,
    )
    expect(container.querySelector('strong')).toHaveTextContent('forte')
    expect(container.querySelector('em')).toHaveTextContent('fraco')
    expect(container.querySelector('code')).toHaveTextContent('cod')
    expect(container.querySelector('del')).toHaveTextContent('fora')
  })

  it('aninha marcações', () => {
    const { container } = render(<Markdown>{'**a *b* c**'}</Markdown>)
    expect(container.querySelector('strong em')).toHaveTextContent('b')
  })

  it('não interpreta HTML como markup — texto é texto', () => {
    const { container } = render(<Markdown>{'<script>alert(1)</script>'}</Markdown>)
    expect(container.querySelector('script')).toBeNull()
    expect(screen.getByText('<script>alert(1)</script>')).toBeInTheDocument()
  })

  it('devolve o texto cru quando não há marcação', () => {
    render(<Markdown>{'sem nada'}</Markdown>)
    expect(screen.getByText('sem nada')).toBeInTheDocument()
  })

  it('aceita vazio sem quebrar', () => {
    const { container } = render(<Markdown>{null}</Markdown>)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('Markdown — casos reais do seed', () => {
  it('negrito com itálico dentro, como nas tabelas de gramática', () => {
    const { container } = render(<Markdown>{'A taxi is **faster than** a bus.'}</Markdown>)
    expect(container.querySelector('strong')).toHaveTextContent('faster than')
  })

  it('código não interpreta o que está dentro', () => {
    const { container } = render(<Markdown>{'Complete: `**____**` aqui'}</Markdown>)
    expect(container.querySelector('code')).toHaveTextContent('**____**')
    expect(container.querySelector('code strong')).toBeNull()
  })

  it('itálico isolado não engole o negrito vizinho', () => {
    const { container } = render(<Markdown>{'**-er than** e *more … than*'}</Markdown>)
    expect(container.querySelector('strong')).toHaveTextContent('-er than')
    expect(container.querySelector('em')).toHaveTextContent('more … than')
  })
})
