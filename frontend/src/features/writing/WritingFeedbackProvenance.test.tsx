import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { WritingFeedback } from '../../api/client'
import { WritingFeedbackProvenance } from './WritingFeedbackProvenance'

const feedback: WritingFeedback = {
  source_text_hash: 'a'.repeat(64),
  id: 1, word_count: 10, sentence_count: 2, ready: true, checks: [],
  algorithm_version: 'writing-rules-v2', rubric_version: `sha256:${'a'.repeat(64)}`,
  rubric_snapshot: { schema_version: 2 }, evaluation_scope: 'Não garante gramática correta.',
  analysis_mode: 'deterministic', automated: true, evaluation_only: false,
  provider: null, assisted_summary: null, assisted_suggestions: [], assisted_confidence: null,
  low_confidence: false, assisted_cost_microusd: 0, assisted_error_code: null,
  human_rating: null, created_at: '2026-10-13T12:00:00Z',
}

describe('WritingFeedbackProvenance', () => {
  it('identifica algoritmo, rubrica e limites do resultado novo', () => {
    render(<WritingFeedbackProvenance feedback={feedback} />)
    expect(screen.getByText(/Regra writing-rules-v2/)).toBeInTheDocument()
    expect(screen.getByTitle(feedback.rubric_version!)).toHaveTextContent('aaaaaaaaaaaa')
    expect(screen.getByText('Não garante gramática correta.')).toBeInTheDocument()
    expect(screen.queryByText(/resultado preservado/)).not.toBeInTheDocument()
  })

  it('explica limitações históricas sem afirmar que o resultado foi corrigido', () => {
    render(<WritingFeedbackProvenance feedback={{ ...feedback, algorithm_version: 'legacy-v1', rubric_version: null, rubric_snapshot: null }} />)
    expect(screen.getByText('Regra anterior · resultado preservado')).toBeInTheDocument()
    expect(screen.getByText(/O resultado original não foi recalculado/)).toBeInTheDocument()
    expect(screen.queryByTitle(`sha256:${'a'.repeat(64)}`)).not.toBeInTheDocument()
  })
})
