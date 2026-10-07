import { Link } from 'react-router-dom'
import { useLessons } from '../api/queries'
import { Carregando, Erro } from '../components/States'

export function MapPage() {
  const { data, isPending, error, refetch } = useLessons()

  if (isPending) return <Carregando oque="as aulas" />
  if (error) return <Erro erro={error} aoTentarDeNovo={() => void refetch()} />

  return (
    <>
      <p className="eyebrow">Let's Learn English · Level 1 · VOA Learning English</p>
      <h1>Mapa do bloco 31–40</h1>
      <p className="lead">
        Dez aulas que montam, em sequência, o sistema de comparação e o sistema de futuro do inglês.
        A 31 abre com o comparativo, a 38 fecha com o superlativo e a 40 estende tudo para os
        advérbios — vale estudar na ordem.
      </p>

      <div className="arc">
        <div className="ahead">
          <span>Aula</span>
          <span>Título</span>
          <span>Foco gramatical</span>
          <span>Série</span>
        </div>
        {data.map((a) => (
          <Link className="arow" key={a.number} to={`/aulas/${a.number}`}>
            <span className="an">{a.number}</span>
            <span className="at">{a.title}</span>
            <span className="ag">{a.grammar_tag}</span>
            <span className="ap">{a.story_note ?? '—'}</span>
          </Link>
        ))}
      </div>
    </>
  )
}
