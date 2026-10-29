import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DialogueTurnView } from './DialogueTurnView'
import { turnFixture } from './dialogueFixtures'

describe('critérios históricos do turno', () => {
  it('mostra cobertura armazenada mesmo depois da remoção do texto', () => {
    const turn = turnFixture()
    turn.transcript = null
    turn.check_details = {
      target_terms: [{ text: 'bus', covered: true }, { text: 'train', covered: false }],
      grammar_patterns: [{ text: 'I take', covered: true }, { text: 'I go', covered: false }],
    }
    render(<DialogueTurnView turn={turn} guided disabled={false} onRate={vi.fn()} onSpeak={vi.fn()} />)
    expect(screen.getByText('bus').parentElement).toHaveTextContent('Termos usados: bus.')
    expect(screen.getByText('train').parentElement).toHaveTextContent('Termos não identificados: train.')
    expect(screen.getByText('I take').parentElement).toHaveTextContent('Padrões identificados: I take.')
    expect(screen.getByText('I go').parentElement).toHaveTextContent('Padrões não identificados: I go.')
    expect(screen.getByText('Vocabulário solicitado: atendido.')).toBeInTheDocument()
    expect(screen.getByText('Texto removido conforme a retenção.')).toBeInTheDocument()
  })

  it('não inventa detalhes legados a partir da transcrição ou do booleano', () => {
    const turn = turnFixture()
    turn.check_details = null
    render(<DialogueTurnView turn={turn} guided disabled={false} onRate={vi.fn()} onSpeak={vi.fn()} />)
    expect(screen.getByText('Detalhamento dos critérios indisponível para este turno.')).toBeInTheDocument()
    expect(screen.queryByText(/Termos usados/)).not.toBeInTheDocument()
  })

  it('omite critérios não solicitados e explica a ausência quando nenhum termo apareceu', () => {
    const turn = turnFixture()
    turn.check_details = { target_terms: [{ text: 'train', covered: false }], grammar_patterns: [] }
    turn.checks.target_terms_missing = false
    render(<DialogueTurnView turn={turn} guided={false} disabled={false} onRate={vi.fn()} onSpeak={vi.fn()} />)
    expect(screen.getByText('Termos usados: nenhum.')).toBeInTheDocument()
    expect(screen.queryByText(/Padrões identificados/)).not.toBeInTheDocument()
    expect(screen.getByText('Vocabulário solicitado: a revisar.')).toBeInTheDocument()
  })
})
