import { useMemo, useState } from 'react'
import { useSessao } from '../api/auth'
import { useAllExercises } from '../api/queries'
import { ExerciseCard } from '../components/ExerciseCard'
import { Carregando, Erro } from '../components/States'

/** Uma questão por aula: a primeira de cada uma, para cobrir o escopo disponível. */
function umaPorAula<T extends { lesson_number: number; position: number }>(todos: T[]): T[] {
  const porAula = new Map<number, T>()
  for (const e of todos) {
    const atual = porAula.get(e.lesson_number)
    if (!atual || e.position < atual.position) porAula.set(e.lesson_number, e)
  }
  return [...porAula.values()].sort((a, b) => a.lesson_number - b.lesson_number)
}

export function TestPage() {
  const { usuario } = useSessao()
  const { data, isPending, error, refetch } = useAllExercises()
  const [respondidos, setRespondidos] = useState<Record<number, boolean>>({})

  const questoes = useMemo(() => (data ? umaPorAula(data) : []), [data])

  if (isPending) return <Carregando oque="a avaliação" />
  if (error) return <Erro erro={error} aoTentarDeNovo={() => void refetch()} />

  const acertos = Object.values(respondidos).filter(Boolean).length
  const feitos = Object.keys(respondidos).length

  return (
    <>
      <p className="eyebrow">Fechamento da unidade</p>
      <h1>Avaliação das aulas disponíveis</h1>
      <p className="lead">
        Uma questão de cada aula. O número ao lado diz de onde ela vem — se errar, volte para aquela
        aula na trilha. A correção é feita pelo servidor.
      </p>

      <div className="stack tight" style={{ marginTop: 26 }}>
        {questoes.map((q, i) => (
          <div key={q.id}>
            <p className="origem">Aula {q.lesson_number}</p>
            <ExerciseCard
              exercicio={q}
              numero={i + 1}
              userId={usuario?.id ?? 0}
              aoResponder={(ok) => setRespondidos((r) => ({ ...r, [q.id]: ok }))}
            />
          </div>
        ))}
      </div>

      <p className="score" role="status">
        <span className="n">
          {acertos}/{questoes.length}
        </span>
        <span className="lbl">
          {feitos === 0 ? 'nenhuma respondida ainda' : `acertos em ${feitos} respondidas`}
        </span>
      </p>
    </>
  )
}
