import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { api, type Exercise } from '../api/client'
import { Markdown } from './Markdown'

type Veredito =
  | { tipo: 'nada' }
  | { tipo: 'certo'; explicacao: string }
  | { tipo: 'errado'; explicacao: string }
  | { tipo: 'revelado'; respostas: string[]; explicacao: string }
  | { tipo: 'falhou'; mensagem: string }

/**
 * Um exercício de completar.
 *
 * A correção é do servidor: a resposta certa não faz parte do contrato de
 * leitura, então mandá-la ao navegador para o JavaScript comparar seria
 * publicar o gabarito. O botão "Resposta" pede o gabarito explicitamente.
 */
export function ExerciseCard({
  exercicio,
  numero,
  aoResponder,
}: {
  exercicio: Exercise
  numero: number
  aoResponder?: (acertou: boolean) => void
}) {
  const [texto, setTexto] = useState('')
  const [veredito, setVeredito] = useState<Veredito>({ tipo: 'nada' })

  const conferir = useMutation({
    mutationFn: async (answer: string) => {
      const { data, response } = await api.POST('/api/exercises/{exercise_id}/check', {
        params: { path: { exercise_id: exercicio.id } },
        body: { answer },
      })
      if (!data) throw new Error(`A API respondeu ${response?.status ?? 'nada'} ao conferir.`)
      return data
    },
    onSuccess: (d) => {
      setVeredito({ tipo: d.correct ? 'certo' : 'errado', explicacao: d.explanation })
      aoResponder?.(d.correct)
    },
    onError: (e: Error) => setVeredito({ tipo: 'falhou', mensagem: e.message }),
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
  const ocupado = conferir.isPending || revelar.isPending

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
          if (texto.trim()) conferir.mutate(texto)
        }}
      >
        <input
          type="text"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder="sua resposta"
          aria-label={`Resposta do exercício ${numero}`}
          autoComplete="off"
          spellCheck={false}
        />
        <button type="submit" disabled={ocupado || !texto.trim()}>
          Verificar
        </button>
        <button type="button" className="ghost" onClick={() => revelar.mutate()} disabled={ocupado}>
          Resposta
        </button>
      </form>

      {veredito.tipo !== 'nada' && (
        <p className={`fb ${veredito.tipo}`} role="status">
          {veredito.tipo === 'certo' && (
            <>
              <span className="tag">Correto</span>
              <span className="why">
                <Markdown>{veredito.explicacao}</Markdown>
              </span>
            </>
          )}
          {veredito.tipo === 'errado' && (
            <>
              <span className="tag">Ainda não</span>
              <span className="why">
                <Markdown>{veredito.explicacao}</Markdown> Tente de novo ou clique em{' '}
                <strong>Resposta</strong>.
              </span>
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
        </p>
      )}
    </div>
  )
}
