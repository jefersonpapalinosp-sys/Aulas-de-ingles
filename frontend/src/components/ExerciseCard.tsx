import { useMutation, useQueryClient } from '@tanstack/react-query'
import { type Ref, useRef, useState } from 'react'
import { api, type AttemptFeedback, type Exercise, type ExerciseHint } from '../api/client'
import { queueAttempt } from '../features/offline/attemptQueue'
import type {
  ExerciseActivityEvent,
  PracticeSessionItem,
} from '../features/practice/types'
import { Markdown } from './Markdown'

type Veredito =
  | { tipo: 'nada' }
  | { tipo: 'certo'; explicacao: string | null }
  | { tipo: 'errado'; feedback: AttemptFeedback }
  | { tipo: 'revelado'; respostas: string[]; explicacao: string }
  | { tipo: 'fila' }
  | { tipo: 'falhou'; mensagem: string }

function classificationAnswer(items: string[], assignments: Record<string, string>): string {
  if (items.some((item) => !assignments[item])) return ''
  return JSON.stringify(
    Object.fromEntries([...items].sort().map((item) => [item, assignments[item]])),
  )
}

function classificationEntries(answer: string): Array<[string, string]> | null {
  try {
    const value: unknown = JSON.parse(answer)
    if (!value || Array.isArray(value) || typeof value !== 'object') return null
    const entries = Object.entries(value)
    return entries.every((entry) => typeof entry[1] === 'string')
      ? (entries as Array<[string, string]>)
      : null
  } catch {
    return null
  }
}

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
 * Motor único das atividades objetivas: lacuna, escolha, transformação,
 * ordenação por botões, classificação por selects e ditado textual.
 *
 * A correção é do servidor: a resposta certa não faz parte do contrato de
 * leitura, então mandá-la ao navegador para o JavaScript comparar seria
 * publicar o gabarito. O botão "Resposta" pede o gabarito explicitamente.
 *
 * Cada tentativa é gravada com idempotência e alimenta o deck de revisão
 * quando o erro corresponde a um item de vocabulário.
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
  const qc = useQueryClient()

  function saveForLater(answer: string, key: string) {
    queueAttempt({
      userId,
      exerciseId: exercicio.id,
      answer,
      idempotencyKey: key,
      createdAt: new Date().toISOString(),
      sessionId: practiceSessionId,
      courseSlug,
      lessonNumber,
    })
  }

  const conferir = useMutation({
    // A própria mutationFn decide entre API e fila local. Sem `always`, o
    // TanStack pausa a mutation ao receber o evento offline e esse fallback
    // nunca é executado.
    networkMode: 'always',
    mutationFn: async ({ answer, key }: { answer: string; key: string }) => {
      if (!navigator.onLine) {
        saveForLater(answer, key)
        return { data: null, key }
      }
      let result
      try {
        result = await api.POST('/api/exercises/{exercise_id}/attempt', {
          params: { path: { exercise_id: exercicio.id } },
          body: {
            answer,
            idempotency_key: key,
            ...(practiceSessionId === undefined
              ? {}
              : { practice_session_id: practiceSessionId }),
          },
        })
      } catch (error) {
        // fetch rejeita com TypeError quando a conexão cai entre o precheck e
        // a resposta. Erros HTTP chegam normalmente em `response` abaixo e
        // não devem entrar na fila offline.
        if (
          error instanceof TypeError ||
          (error instanceof DOMException && error.name === 'NetworkError')
        ) {
          saveForLater(answer, key)
          return { data: null, key }
        }
        throw error
      }
      const { data, response } = result
      if (!data && !response) {
        saveForLater(answer, key)
        return { data: null, key }
      }
      if (!data) throw new Error(`A API respondeu ${response?.status ?? 'nada'} ao conferir.`)
      return { data, key }
    },
    onSuccess: ({ data, key }) => {
      if (!data) {
        setVeredito({ tipo: 'fila' })
        onActivity?.({
          type: 'attempt',
          exerciseId: exercicio.id,
          status: 'queued',
          idempotencyKey: key,
          correct: null,
        })
        return
      }
      setVeredito(
        data.correct
          ? { tipo: 'certo', explicacao: data.explanation }
          : { tipo: 'errado', feedback: data.feedback },
      )
      if (!data.correct) setErrouAntes(true)
      aoResponder?.(data.correct)
      onActivity?.({
        type: 'attempt',
        exerciseId: exercicio.id,
        status: data.correct ? 'correct' : 'incorrect',
        idempotencyKey: key,
        correct: data.correct,
      })
      // Errar pode ter semeado o deck: trilha e recomendação de Hoje precisam saber.
      void qc.invalidateQueries({ queryKey: ['progress'] })
      void qc.invalidateQueries({ queryKey: ['review'] })
      void qc.invalidateQueries({ queryKey: ['today'] })
      void qc.invalidateQueries({ queryKey: ['course-completion'] })
    },
    onError: (e: Error) => setVeredito({ tipo: 'falhou', mensagem: e.message }),
  })

  const pedirDica = useMutation({
    mutationFn: async (level: number) => {
      if (practiceSessionId !== undefined) {
        const { data, response } = await api.POST(
          '/api/practice-sessions/{session_id}/items/{exercise_id}/hints/{level}',
          {
            params: {
              path: {
                session_id: practiceSessionId,
                exercise_id: exercicio.id,
                level,
              },
            },
          },
        )
        if (!data) {
          const message =
            response?.status === 409
              ? 'Faça uma tentativa antes de abrir a próxima dica.'
              : `A API respondeu ${response?.status ?? 'nada'} ao buscar a dica.`
          throw new Error(message)
        }
        return { hint: { level: data.level, content: data.content }, level }
      }
      const { data, response } = await api.GET('/api/exercises/{exercise_id}/hints/{level}', {
        params: { path: { exercise_id: exercicio.id, level } },
      })
      if (!data) {
        const message =
          response?.status === 409
            ? 'Faça uma tentativa antes de abrir a próxima dica.'
            : `A API respondeu ${response?.status ?? 'nada'} ao buscar a dica.`
        throw new Error(message)
      }
      return { hint: data, level }
    },
    onSuccess: ({ hint, level }) => {
      setDicas((current) => [...current.filter((item) => item.level !== hint.level), hint])
      onActivity?.({ type: 'hint', exerciseId: exercicio.id, level })
    },
  })

  const revelar = useMutation({
    mutationFn: async () => {
      if (practiceSessionId !== undefined) {
        const { data, response } = await api.POST(
          '/api/practice-sessions/{session_id}/items/{exercise_id}/reveal',
          {
            params: {
              path: { session_id: practiceSessionId, exercise_id: exercicio.id },
            },
          },
        )
        if (!data) throw new Error(`A API respondeu ${response?.status ?? 'nada'} ao buscar.`)
        return data
      }
      const { data, response } = await api.GET('/api/exercises/{exercise_id}/answer', {
        params: { path: { exercise_id: exercicio.id } },
      })
      if (!data) throw new Error(`A API respondeu ${response?.status ?? 'nada'} ao buscar.`)
      return data
    },
    onSuccess: (d) => {
      setVeredito({ tipo: 'revelado', respostas: d.answers, explicacao: d.explanation })
      onActivity?.({ type: 'reveal', exerciseId: exercicio.id })
    },
    onError: (e: Error) => setVeredito({ tipo: 'falhou', mensagem: e.message }),
  })

  const estado =
    veredito.tipo === 'certo' ? 'bom' : veredito.tipo === 'errado' ? 'ruim' : ''
  const ocupado = conferir.isPending || revelar.isPending || pedirDica.isPending
  const finalizado =
    veredito.tipo === 'certo' || veredito.tipo === 'revelado' || veredito.tipo === 'fila'
  const nextHintLevel = dicas.length + 1
  const supportedTypes = new Set([
    'gap_fill',
    'multiple_choice',
    'transformation',
    'reorder',
    'dictation',
    'classification',
  ])
  const classificationItems = exercicio.classification_items ?? []
  const classificationCategories = exercicio.classification_categories ?? []
  const classificationReady =
    exercicio.activity_type !== 'classification' ||
    (classificationItems.length > 0 && classificationCategories.length >= 2)
  const supported = supportedTypes.has(exercicio.activity_type) && classificationReady

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
      <h3 className="q" ref={promptRef} tabIndex={-1}>
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
            if (texto.trim() && !finalizado) {
              conferir.mutate({ answer: texto, key: crypto.randomUUID() })
            }
          }}
        >
        {exercicio.activity_type === 'classification' ? (
          <fieldset className="classification-activity">
            <legend>Classifique cada item</legend>
            <div className="classification-grid">
              {classificationItems.map((item, index) => {
                const selectId = `classification-${exercicio.id}-${index}`
                return (
                  <label htmlFor={selectId} key={item}>
                    <span>{item}</span>
                    <select
                      id={selectId}
                      ref={index === 0 ? firstClassificationRef : undefined}
                      value={classificacoes[item] ?? ''}
                      disabled={finalizado}
                      onChange={(event) => atualizarClassificacao(item, event.target.value)}
                    >
                      <option value="">Selecione uma categoria</option>
                      {classificationCategories.map((category) => (
                        <option key={category} value={category}>
                          {category}
                        </option>
                      ))}
                    </select>
                  </label>
                )
              })}
            </div>
          </fieldset>
        ) : exercicio.activity_type === 'reorder' && exercicio.options ? (
          <fieldset className="reorder-activity">
            <legend>Monte a frase</legend>
            <div className="reorder-answer" aria-label="Frase montada">
              {ordem.length === 0 ? (
                <span>Escolha as palavras na ordem correta</span>
              ) : (
                ordem.map((word, index) => (
                  <button
                    type="button"
                    key={`${word}-${index}`}
                    aria-label={`Remover ${word}`}
                    disabled={finalizado}
                    onClick={() => atualizarOrdem(ordem.filter((_, itemIndex) => itemIndex !== index))}
                  >
                    {word}
                  </button>
                ))
              )}
            </div>
            <div className="reorder-options" aria-label="Palavras disponíveis">
              {exercicio.options.map((word, index) => (
                <button
                  type="button"
                  key={`${word}-${index}`}
                  ref={index === 0 ? firstReorderRef : undefined}
                  disabled={finalizado || ordem.includes(word)}
                  aria-label={`Adicionar ${word}`}
                  onClick={() => atualizarOrdem([...ordem, word])}
                >
                  {word}
                </button>
              ))}
            </div>
          </fieldset>
        ) : exercicio.activity_type === 'multiple_choice' && exercicio.options ? (
          <fieldset className="choice-options">
            <legend>Escolha uma resposta</legend>
            {exercicio.options.map((option, index) => (
              <label key={option}>
                <input
                  ref={index === 0 ? firstChoiceRef : undefined}
                  type="radio"
                  name={`exercise-${exercicio.id}`}
                  value={option}
                  checked={texto === option}
                  disabled={finalizado}
                  onChange={(event) => setTexto(event.target.value)}
                />
                <span>{option}</span>
              </label>
            ))}
          </fieldset>
        ) : (
          <input
            ref={inputRef}
            type="text"
            value={texto}
            disabled={finalizado}
            onChange={(e) => setTexto(e.target.value)}
            placeholder="sua resposta"
            aria-label={`Resposta do exercício ${numero}`}
            autoComplete="off"
            spellCheck={false}
          />
        )}
        <button type="submit" disabled={ocupado || finalizado || !texto.trim()}>
          Verificar
        </button>
        {exercicio.hint_count > 0 && nextHintLevel <= exercicio.hint_count && (
          <button
            type="button"
            className="ghost"
            disabled={ocupado || finalizado || (nextHintLevel > 1 && !errouAntes)}
            onClick={() => pedirDica.mutate(nextHintLevel)}
          >
            Dica {nextHintLevel}
          </button>
        )}
        <button
          type="button"
          className="ghost"
          onClick={() => revelar.mutate()}
          disabled={ocupado || finalizado}
        >
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

      {veredito.tipo !== 'nada' && (
        <div className={`fb ${veredito.tipo}`} role="status">
          {veredito.tipo === 'certo' && (
            <>
              <span className="tag">Correto</span>
              {veredito.explicacao && (
                <span className="why">
                  <Markdown>{veredito.explicacao}</Markdown>
                </span>
              )}
            </>
          )}
          {veredito.tipo === 'errado' && (
            <>
              <span className="tag">Ainda não</span>
              <span className="answer-diff" aria-label="Trechos da sua resposta">
                {veredito.feedback.tokens.map((token, index) => (
                  <mark className={token.status} key={`${token.text}-${index}`}>
                    {token.text}
                  </mark>
                ))}
              </span>
              <span className="why">{veredito.feedback.message}</span>
              <button type="button" className="feedback-retry" onClick={tentarNovamente}>
                Tentar novamente
              </button>
            </>
          )}
          {veredito.tipo === 'revelado' && (
            <>
              <span className="tag">Resposta</span>
              {exercicio.activity_type === 'classification' ? (
                <div className="classification-solutions">
                  {veredito.respostas.map((answer, answerIndex) => {
                    const entries = classificationEntries(answer)
                    return entries ? (
                      <dl key={answer} aria-label={`Gabarito ${answerIndex + 1}`}>
                        {entries.map(([item, category]) => (
                          <div key={item}>
                            <dt>{item}</dt>
                            <dd>{category}</dd>
                          </div>
                        ))}
                      </dl>
                    ) : (
                      <strong className="gabarito" key={answer}>{answer}</strong>
                    )
                  })}
                </div>
              ) : (
                <strong className="gabarito">{veredito.respostas.join('  ·  ')}</strong>
              )}
              <span className="why">
                <Markdown>{veredito.explicacao}</Markdown>
              </span>
            </>
          )}
          {veredito.tipo === 'falhou' && (
            <>
              <span className="tag">Erro</span>
              <span className="why">{veredito.mensagem}</span>
            </>
          )}
          {veredito.tipo === 'fila' && (
            <>
              <span className="tag">Na fila</span>
              <span className="why">
                Sua tentativa foi salva neste dispositivo e será corrigida quando a conexão voltar.
              </span>
            </>
          )}
        </div>
      )}
    </div>
  )
}
