import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import {
  api,
  type HistoricalContent,
  type HistoricalEvidenceKind,
} from '../../api/client'

const KIND_LABELS: Record<HistoricalEvidenceKind, string> = {
  exercise: 'Exercício',
  practice: 'Prática',
  writing: 'Escrita',
  speaking: 'Fala',
  checkpoint: 'Checkpoint',
}

function stringField(content: Record<string, unknown>, key: string): string | null {
  return typeof content[key] === 'string' && content[key] ? content[key] : null
}

function numberField(content: Record<string, unknown>, key: string): number | null {
  return typeof content[key] === 'number' ? content[key] : null
}

function objectField(content: Record<string, unknown>, key: string): Record<string, unknown> | null {
  const value = content[key]
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function objectArray(content: Record<string, unknown>, key: string): Record<string, unknown>[] {
  const value = content[key]
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => (
      typeof item === 'object' && item !== null && !Array.isArray(item)
    ))
    : []
}

function resultFields(content: Record<string, unknown>): { answer: string | null; correct: boolean | null } {
  const result = content.result
  if (typeof result !== 'object' || result === null || Array.isArray(result)) {
    return { answer: null, correct: null }
  }
  const record = result as Record<string, unknown>
  return {
    answer: typeof record.answer === 'string' ? record.answer : null,
    correct: typeof record.correct === 'boolean' ? record.correct : null,
  }
}

function CapturedContent({ history }: { history: HistoricalContent }) {
  if (history.status === 'unavailable' || !history.content) {
    return (
      <p className="historical-unavailable">
        O conteúdo original exato não foi capturado. O conteúdo atual não será usado para
        reconstruir esta evidência.
      </p>
    )
  }
  const content = history.content
  const result = resultFields(content)
  const title = stringField(content, 'title')
  const prompt = stringField(content, 'prompt')
  const objective = stringField(content, 'objective')
  const textEn = stringField(content, 'text_en')
  const explanation = stringField(content, 'explanation')
  const contentVersion = numberField(content, 'content_version')
  const lessonVersion = numberField(content, 'lesson_version')
  const rubricVersion = stringField(content, 'rubric_version')
  const algorithmVersion = stringField(content, 'algorithm_version')
  const rubric = objectField(content, 'rubric')
  const rubricTitle = rubric ? stringField(rubric, 'title') : null
  const rubricInstructions = rubric ? stringField(rubric, 'instructions') : null
  const rubricMinWords = rubric ? numberField(rubric, 'min_words') : null
  const rubricMinSentences = rubric ? numberField(rubric, 'min_sentences') : null
  const questions = objectArray(content, 'questions')
  const answers = new Map(
    objectArray(content, 'result')
      .filter((item) => typeof item.question_id === 'number')
      .map((item) => [item.question_id as number, item]),
  )

  return (
    <div className="historical-content-body">
      {title && <p><strong>Título capturado:</strong> {title}</p>}
      {prompt && <p><strong>Enunciado capturado:</strong> <span lang="en">{prompt}</span></p>}
      {objective && <p><strong>Objetivo capturado:</strong> {objective}</p>}
      {textEn && <p><strong>Trecho capturado:</strong> <span lang="en">{textEn}</span></p>}
      {result.answer && <p><strong>Resposta registrada:</strong> <span lang="en">{result.answer}</span></p>}
      {result.correct !== null && (
        <p><strong>Resultado registrado:</strong> {result.correct ? 'correto' : 'incorreto'}</p>
      )}
      {explanation && <p><strong>Explicação capturada:</strong> {explanation}</p>}
      {rubricTitle && <p><strong>Proposta capturada:</strong> {rubricTitle}</p>}
      {rubricInstructions && <p><strong>Instruções capturadas:</strong> {rubricInstructions}</p>}
      {(rubricMinWords !== null || rubricMinSentences !== null) && (
        <p>
          <strong>Mínimos capturados:</strong>{' '}
          {rubricMinWords ?? '—'} palavras · {rubricMinSentences ?? '—'} frases
        </p>
      )}
      {questions.length > 0 && (
        <div className="historical-question-list">
          <strong>Questões e resultados capturados:</strong>
          <ol>
            {questions.map((question, index) => {
              const identifier = typeof question.id === 'number' ? question.id : index
              const answer = typeof identifier === 'number' ? answers.get(identifier) : undefined
              const questionPrompt = stringField(question, 'prompt') ?? `Questão ${index + 1}`
              return (
                <li key={identifier}>
                  <span lang="en">{questionPrompt}</span>
                  {typeof answer?.answer === 'string' && (
                    <small>Resposta: <span lang="en">{answer.answer}</span></small>
                  )}
                  {typeof answer?.correct === 'boolean' && (
                    <small>Resultado: {answer.correct ? 'correto' : 'incorreto'}</small>
                  )}
                </li>
              )
            })}
          </ol>
        </div>
      )}
      <dl className="historical-version-list">
        {contentVersion !== null && <><dt>Versão do checkpoint</dt><dd>{contentVersion}</dd></>}
        {lessonVersion !== null && <><dt>Versão da aula</dt><dd>{lessonVersion}</dd></>}
        {rubricVersion && <><dt>Versão da rubrica</dt><dd>{rubricVersion}</dd></>}
        {algorithmVersion && <><dt>Regra de avaliação</dt><dd>{algorithmVersion}</dd></>}
      </dl>
      <p className="muted">{history.note}</p>
    </div>
  )
}

export function HistoricalContentDetails({
  kind,
  evidenceId,
}: {
  kind: HistoricalEvidenceKind
  evidenceId: number
}) {
  const [open, setOpen] = useState(false)
  const query = useQuery({
    queryKey: ['historical-content', kind, evidenceId],
    queryFn: async () => {
      const { data } = await api.GET('/api/me/history/{kind}/{evidence_id}/content', {
        params: { path: { kind, evidence_id: evidenceId } },
      })
      if (!data) throw new Error('Conteúdo histórico indisponível.')
      return data
    },
    enabled: open,
    retry: false,
  })

  return (
    <details className="historical-content-details" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>Consultar conteúdo de {KIND_LABELS[kind].toLocaleLowerCase('pt-BR')}</summary>
      {open && query.isPending && <p>Carregando conteúdo capturado…</p>}
      {query.isError && <p role="alert">Não foi possível carregar este conteúdo histórico.</p>}
      {query.data && <CapturedContent history={query.data} />}
    </details>
  )
}
