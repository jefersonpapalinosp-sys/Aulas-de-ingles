import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { api, type AttemptFeedback, type Exercise, type ExerciseHint } from '../api/client'
import { queueAttempt } from '../features/offline/attemptQueue'
import { Markdown } from './Markdown'

type Veredito =
  | { tipo: 'nada' }
  | { tipo: 'certo'; explicacao: string | null }
  | { tipo: 'errado'; feedback: AttemptFeedback }
  | { tipo: 'revelado'; respostas: string[]; explicacao: string }
  | { tipo: 'fila' }
  | { tipo: 'falhou'; mensagem: string }

/**
 * Uma atividade objetiva, inicialmente de lacuna ou múltipla escolha.
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
}: {
  exercicio: Exercise
  numero: number
  userId: number
  aoResponder?: (acertou: boolean) => void
}) {
  const [texto, setTexto] = useState('')
  const [veredito, setVeredito] = useState<Veredito>({ tipo: 'nada' })
  const [dicas, setDicas] = useState<ExerciseHint[]>([])
  const [errouAntes, setErrouAntes] = useState(false)
  const [ordem, setOrdem] = useState<string[]>([])
  const inputRef = useRef<HTMLInputElement>(null)
  const qc = useQueryClient()

  const conferir = useMutation({
    mutationFn: async ({ answer, key }: { answer: string; key: string }) => {
      if (!navigator.onLine) {
        queueAttempt({
          userId,
          exerciseId: exercicio.id,
          answer,
          idempotencyKey: key,
          createdAt: new Date().toISOString(),
        })
        return null
      }
      const { data, response } = await api.POST('/api/exercises/{exercise_id}/attempt', {
        params: { path: { exercise_id: exercicio.id } },
        body: { answer, idempotency_key: key },
      })
      if (!data && !response) {
        queueAttempt({
          userId,
          exerciseId: exercicio.id,
          answer,
          idempotencyKey: key,
          createdAt: new Date().toISOString(),
        })
        return null
      }
      if (!data) throw new Error(`A API respondeu ${response?.status ?? 'nada'} ao conferir.`)
      return data
    },
    onSuccess: (d) => {
      if (!d) {
        setVeredito({ tipo: 'fila' })
        return
      }
      setVeredito(
        d.correct
          ? { tipo: 'certo', explicacao: d.explanation }
          : { tipo: 'errado', feedback: d.feedback },
      )
      if (!d.correct) setErrouAntes(true)
      aoResponder?.(d.correct)
      // Errar pode ter semeado o deck: o contador da trilha precisa saber.
      void qc.invalidateQueries({ queryKey: ['progress'] })
      void qc.invalidateQueries({ queryKey: ['review'] })
    },
    onError: (e: Error) => setVeredito({ tipo: 'falhou', mensagem: e.message }),
  })

  const pedirDica = useMutation({
    mutationFn: async (level: number) => {
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
      return data
    },
    onSuccess: (hint) =>
      setDicas((current) => [...current.filter((item) => item.level !== hint.level), hint]),
  })

  const revelar = useMutation({
    mutationFn: async () => {
      const { data, response } = await api.GET('/api/exercises/{exercise_id}/answer', {
        params: { path: { exercise_id: exercicio.id } },
      })
      if (!data) throw new Error(`A API respondeu ${response?.status ?? 'nada'} ao buscar.`)
      return data
    },
    onSuccess: (d) =>
      setVeredito({ tipo: 'revelado', respostas: d.answers, explicacao: d.explanation }),
    onError: (e: Error) => setVeredito({ tipo: 'falhou', mensagem: e.message }),
  })

  const estado =
    veredito.tipo === 'certo' ? 'bom' : veredito.tipo === 'errado' ? 'ruim' : ''
  const ocupado = conferir.isPending || revelar.isPending || pedirDica.isPending
  const nextHintLevel = dicas.length + 1

  function tentarNovamente() {
    setVeredito({ tipo: 'nada' })
    inputRef.current?.focus()
  }

  function atualizarOrdem(next: string[]) {
    setOrdem(next)
    setTexto(next.join(' '))
  }

  return (
    <div className={`ex ${estado}`}>
      <p className="q">
        <span className="qn">{numero}.</span>
        <span>
          <Markdown>{exercicio.prompt}</Markdown>
          {exercicio.hint && <em className="dica"> ({exercicio.hint})</em>}
        </span>
      </p>

      <form
        className="ex-row"
        onSubmit={(e) => {
          e.preventDefault()
          if (texto.trim()) conferir.mutate({ answer: texto, key: crypto.randomUUID() })
        }}
      >
        {exercicio.activity_type === 'reorder' && exercicio.options ? (
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
                    onClick={() => atualizarOrdem(ordem.filter((_, itemIndex) => itemIndex !== index))}
                  >
                    {word}
                  </button>
                ))
              )}
            </div>
            <div className="reorder-options" aria-label="Palavras disponíveis">
              {exercicio.options.map((word) => (
                <button
                  type="button"
                  key={word}
                  disabled={ordem.includes(word)}
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
            {exercicio.options.map((option) => (
              <label key={option}>
                <input
                  type="radio"
                  name={`exercise-${exercicio.id}`}
                  value={option}
                  checked={texto === option}
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
            onChange={(e) => setTexto(e.target.value)}
            placeholder="sua resposta"
            aria-label={`Resposta do exercício ${numero}`}
            autoComplete="off"
            spellCheck={false}
          />
        )}
        <button type="submit" disabled={ocupado || !texto.trim()}>
          Verificar
        </button>
        {exercicio.hint_count > 0 && nextHintLevel <= exercicio.hint_count && (
          <button
            type="button"
            className="ghost"
            disabled={ocupado || (nextHintLevel > 1 && !errouAntes)}
            onClick={() => pedirDica.mutate(nextHintLevel)}
          >
            Dica {nextHintLevel}
          </button>
        )}
        <button type="button" className="ghost" onClick={() => revelar.mutate()} disabled={ocupado}>
          Resposta
        </button>
      </form>

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
              <strong className="gabarito">{veredito.respostas.join('  ·  ')}</strong>
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
