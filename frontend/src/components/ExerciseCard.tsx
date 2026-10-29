import { type Ref, useId, useRef, useState } from 'react'
import type { Exercise, ExerciseHint } from '../api/client'
import {
  classificationAnswer,
  SUPPORTED_ACTIVITY_TYPES,
} from '../features/exercise/classification'
import { useExerciseActions } from '../features/exercise/exerciseActions'
import {
  ChoiceInput,
  ClassificationInput,
  ReorderInput,
  TextAnswerInput,
} from '../features/exercise/ExerciseInputs'
import { ExerciseVerdict, type Veredito } from '../features/exercise/ExerciseVerdict'
import type { ExerciseActivityEvent, PracticeSessionItem } from '../features/practice/types'
import { Markdown } from './Markdown'

/** Estado inicial vindo da sessão: quem volta a um item já respondido vê o que
 * respondeu, e não um formulário em branco. */
function initialVerdict(item: PracticeSessionItem | undefined, queued: boolean): Veredito {
  if (queued) return { tipo: 'fila' }
  if (!item) return { tipo: 'nada' }
  if (item.answer_revealed) {
    return {
      tipo: 'revelado',
      respostas: item.answers ?? [],
      explicacao: item.explanation ?? 'Resposta revelada.',
    }
  }
  if (item.outcome === 'first_try_correct' || item.outcome === 'corrected') {
    return { tipo: 'certo', explicacao: item.explanation }
  }
  if (item.last_feedback && item.attempt_count > 0) {
    return { tipo: 'errado', feedback: item.last_feedback }
  }
  return { tipo: 'nada' }
}

/**
 * Compõe uma atividade objetiva: lacuna, escolha, transformação, ordenação por
 * botões, classificação por selects e ditado textual.
 *
 * As ações estão em `features/exercise/exerciseActions.ts`, o campo de cada
 * tipo em `ExerciseInputs.tsx` e o veredito em `ExerciseVerdict.tsx`. Aqui
 * ficam a resposta em digitação, as dicas abertas e o foco depois de "Tentar
 * novamente" — que precisa voltar para o campo certo de cada tipo.
 */
export function ExerciseCard({
  exercicio,
  numero,
  userId,
  aoResponder,
  practiceSessionId,
  courseSlug,
  lessonNumber,
  initialSessionItem,
  initialQueued = false,
  onActivity,
  promptRef,
}: {
  exercicio: Exercise
  numero: number
  userId: number
  aoResponder?: (acertou: boolean) => void
  practiceSessionId?: number
  courseSlug?: string
  lessonNumber?: number
  initialSessionItem?: PracticeSessionItem
  initialQueued?: boolean
  onActivity?: (event: ExerciseActivityEvent) => void
  promptRef?: Ref<HTMLHeadingElement>
}) {
  const id = useId()
  const [texto, setTexto] = useState('')
  const [veredito, setVeredito] = useState<Veredito>(() =>
    initialVerdict(initialSessionItem, initialQueued),
  )
  const [dicas, setDicas] = useState<ExerciseHint[]>(initialSessionItem?.opened_hints ?? [])
  const [errouAntes, setErrouAntes] = useState(
    (initialSessionItem?.attempt_count ?? 0) > 0 && !initialSessionItem?.first_try_correct,
  )
  const [ordem, setOrdem] = useState<string[]>([])
  const [classificacoes, setClassificacoes] = useState<Record<string, string>>({})
  const inputRef = useRef<HTMLInputElement>(null)
  const firstChoiceRef = useRef<HTMLInputElement>(null)
  const firstReorderRef = useRef<HTMLButtonElement>(null)
  const firstClassificationRef = useRef<HTMLSelectElement>(null)
  const pendingSubmission = useRef<{ answer: string; key: string } | null>(null)

  const { conferir, pedirDica, revelar, ocupado } = useExerciseActions({
    exercicio,
    userId,
    practiceSessionId,
    courseSlug,
    lessonNumber,
    onVerdict: setVeredito,
    onHint: (hint) => setDicas((current) => [...current.filter((item) => item.level !== hint.level), hint]),
    onWrong: () => setErrouAntes(true),
    onAnswered: aoResponder,
    onActivity,
  })

  const estado = veredito.tipo === 'certo' ? 'bom' : veredito.tipo === 'errado' ? 'ruim' : ''
  const finalizado =
    veredito.tipo === 'certo' || veredito.tipo === 'revelado' || veredito.tipo === 'fila'
  const nextHintLevel = dicas.length + 1
  const classificationItems = exercicio.classification_items ?? []
  const classificationCategories = exercicio.classification_categories ?? []
  const classificationReady =
    exercicio.activity_type !== 'classification' ||
    (classificationItems.length > 0 && classificationCategories.length >= 2)
  const supported = SUPPORTED_ACTIVITY_TYPES.has(exercicio.activity_type) && classificationReady
  const accessibility = { description: `${id}-prompt ${id}-verdict`, invalid: veredito.tipo === 'errado' }
  const bloqueado = finalizado || ocupado

  function tentarNovamente() {
    setVeredito({ tipo: 'nada' })
    if (exercicio.activity_type === 'multiple_choice') firstChoiceRef.current?.focus()
    else if (exercicio.activity_type === 'reorder') firstReorderRef.current?.focus()
    else if (exercicio.activity_type === 'classification') firstClassificationRef.current?.focus()
    else inputRef.current?.focus()
  }

  function atualizarOrdem(next: string[]) {
    setOrdem(next)
    setTexto(next.join(' '))
  }

  function atualizarClassificacao(item: string, category: string) {
    const next = { ...classificacoes, [item]: category }
    setClassificacoes(next)
    setTexto(classificationAnswer(classificationItems, next))
  }

  return (
    <div className={`ex ${estado}`}>
      <h3 id={`${id}-prompt`} className="q" ref={promptRef} tabIndex={-1}>
        <span className="qn">{numero}.</span>
        <span>
          <Markdown>{exercicio.prompt}</Markdown>
          {exercicio.hint && <em className="dica"> ({exercicio.hint})</em>}
        </span>
      </h3>

      {!supported ? (
        <p className="exercise-unsupported" role="status">
          Esta atividade ainda não é compatível com esta versão do aplicativo.
        </p>
      ) : (
        <form
          className="ex-row"
          onSubmit={(e) => {
            e.preventDefault()
            if (texto.trim() && !bloqueado) {
              if (pendingSubmission.current?.answer !== texto) {
                pendingSubmission.current = { answer: texto, key: crypto.randomUUID() }
              }
              conferir.mutate(pendingSubmission.current)
            }
          }}
        >
          {exercicio.activity_type === 'classification' ? (
            <ClassificationInput
              exercicio={exercicio}
              items={classificationItems}
              categories={classificationCategories}
              assignments={classificacoes}
              disabled={bloqueado}
              {...accessibility}
              firstRef={firstClassificationRef}
              onAssign={atualizarClassificacao}
            />
          ) : exercicio.activity_type === 'reorder' && exercicio.options ? (
            <ReorderInput
              options={exercicio.options}
              ordem={ordem}
              disabled={bloqueado}
              {...accessibility}
              firstRef={firstReorderRef}
              onChange={atualizarOrdem}
            />
          ) : exercicio.activity_type === 'multiple_choice' && exercicio.options ? (
            <ChoiceInput
              exercicio={exercicio}
              options={exercicio.options}
              value={texto}
              disabled={bloqueado}
              {...accessibility}
              firstRef={firstChoiceRef}
              onChange={setTexto}
            />
          ) : (
            <TextAnswerInput
              numero={numero}
              value={texto}
              disabled={bloqueado}
              {...accessibility}
              inputRef={inputRef}
              onChange={setTexto}
            />
          )}
          <button type="submit" disabled={bloqueado || !texto.trim()}>Verificar</button>
          {exercicio.hint_count > 0 && nextHintLevel <= exercicio.hint_count && (
            <button
              type="button"
              className="ghost"
              disabled={bloqueado || (nextHintLevel > 1 && !errouAntes)}
              onClick={() => pedirDica.mutate(nextHintLevel)}
            >
              Dica {nextHintLevel}
            </button>
          )}
          <button type="button" className="ghost" onClick={() => revelar.mutate()} disabled={bloqueado}>
            Resposta
          </button>
        </form>
      )}

      {dicas.length > 0 && (
        <ol className="exercise-hints" aria-label="Dicas abertas">
          {dicas.map((hint) => (
            <li key={hint.level}>
              <strong>Dica {hint.level}</strong> <Markdown>{hint.content}</Markdown>
            </li>
          ))}
        </ol>
      )}
      {pedirDica.isError && <p className="exercise-hint-error" role="alert">{pedirDica.error.message}</p>}

      <div id={`${id}-verdict`}><ExerciseVerdict veredito={veredito} exercicio={exercicio} onRetry={tentarNovamente} /></div>
    </div>
  )
}
