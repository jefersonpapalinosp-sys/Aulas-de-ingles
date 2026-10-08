import { Link, useParams } from 'react-router-dom'
import { useSessao } from '../api/auth'
import { useLesson } from '../api/queries'
import { ExerciseCard } from '../components/ExerciseCard'
import { GrammarBlockView } from '../components/GrammarBlockView'
import { PhraseList, PronunciationList, VocabTable } from '../components/LessonSections'
import { Markdown } from '../components/Markdown'
import { Carregando, Erro } from '../components/States'

function Secao({ n, titulo, children }: { n: string; titulo: string; children: React.ReactNode }) {
  return (
    <section>
      <div className="sec-h">
        <span className="num">{n}</span>
        <h2>{titulo}</h2>
      </div>
      {children}
    </section>
  )
}

export function LessonPage() {
  const { usuario } = useSessao()
  const { numero } = useParams()
  const n = Number(numero)
  const { data, isPending, error, refetch } = useLesson(n)

  if (!Number.isInteger(n)) return <p className="erro">Número de aula inválido.</p>
  if (isPending) return <Carregando oque={`a aula ${n}`} />
  if (error) return <Erro erro={error} aoTentarDeNovo={() => void refetch()} />
  const currentVersion = data.versions[0]

  return (
    <>
      <p className="eyebrow">
        Lesson {data.number} · Let's Learn English Level 1
        {data.story_note && <> · {data.story_note}</>}
      </p>
      <h1>{data.title}</h1>
      <p className="lead">
        <em>{data.title_pt}</em> — <Markdown>{data.lead}</Markdown>
      </p>

      <div className="chips">
        <span className="chip key">{data.grammar_tag}</span>
        {data.focus_points.map((c) => (
          <span className="chip" key={c}>
            <Markdown>{c}</Markdown>
          </span>
        ))}
      </div>

      <section className="lesson-editorial" aria-label="Origem e revisão do conteúdo">
        <div>
          <span>Estratégia de estudo</span>
          <strong>{currentVersion?.learning_strategy ?? 'não informada'}</strong>
        </div>
        <div>
          <span>Revisão editorial</span>
          <strong>
            {currentVersion
              ? `v${currentVersion.version} · ${currentVersion.status === 'reviewed' ? 'revisada' : currentVersion.status}`
              : 'não informada'}
          </strong>
        </div>
        <div>
          <span>Fontes</span>
          <strong>
            {data.content_sources.map((source, index) => (
              <span key={source.kind}>
                {index > 0 && ' · '}
                {source.url ? (
                  <a href={source.url} target="_blank" rel="noopener noreferrer">
                    {source.kind === 'official' ? 'VOA oficial' : source.publisher}
                  </a>
                ) : source.kind === 'authorial' ? (
                  'explicação autoral'
                ) : (
                  source.publisher
                )}
              </span>
            ))}
          </strong>
        </div>
      </section>

      {data.media.some((media) => media.kind === 'conversation_audio') && (
        <div className="study-entry">
          <div>
            <p className="study-kicker">Jornada guiada</p>
            <strong>Estude em cinco etapas e continue de onde parou.</strong>
          </div>
          <Link className="btn" to={`/aulas/${data.number}/estudar`}>
            Começar estudo
          </Link>
        </div>
      )}

      <a className="watch" href={data.voa_url} target="_blank" rel="noopener noreferrer">
        Assistir e ouvir no VOA ↗
      </a>

      <Secao n="01" titulo="Objetivos da aula">
        <ul className="goals">
          {data.goals.map((g, i) => (
            <li key={i}>
              <Markdown>{g}</Markdown>
            </li>
          ))}
        </ul>
      </Secao>

      <Secao n="02" titulo="Gramática">
        <div className="stack">
          {data.grammar_blocks.map((b, i) => (
            <GrammarBlockView bloco={b} key={i} />
          ))}
        </div>
      </Secao>

      <Secao n="03" titulo="Frases da aula">
        <PhraseList frases={data.phrases} />
      </Secao>

      <Secao n="04" titulo="Vocabulário">
        <VocabTable itens={data.vocab} />
      </Secao>

      <Secao n="05" titulo="Pronúncia">
        <PronunciationList notas={data.pronunciation} />
      </Secao>

      <Secao n="06" titulo="Exercícios">
        <div className="stack tight">
          {data.exercises.map((e, i) => (
            <ExerciseCard exercicio={e} numero={i + 1} userId={usuario?.id ?? 0} key={e.id} />
          ))}
        </div>
      </Secao>

      <nav className="navbtns">
        {data.number > 31 ? (
          <Link className="btn ghost" to={`/aulas/${data.number - 1}`}>
            ← Aula {data.number - 1}
          </Link>
        ) : (
          <Link className="btn ghost" to="/">
            ← Mapa do bloco
          </Link>
        )}
        {data.number < 40 ? (
          <Link className="btn ghost" to={`/aulas/${data.number + 1}`}>
            Aula {data.number + 1} →
          </Link>
        ) : (
          <Link className="btn ghost" to="/prova">
            Prova do bloco →
          </Link>
        )}
      </nav>
    </>
  )
}
