import { Link, useParams } from 'react-router-dom'
import { useCourseCurriculum, useLesson } from '../api/queries'
import { GrammarBlockView } from '../components/GrammarBlockView'
import { PhraseList, PronunciationList, VocabTable } from '../components/LessonSections'
import { Markdown } from '../components/Markdown'
import { Carregando, Erro } from '../components/States'
import { adjacentLessons } from '../features/curriculum/curriculum'
import {
  coursePath,
  DEFAULT_COURSE_SLUG,
  lessonPath,
  practicePath,
  studyPath,
  unitPath,
} from '../routing/courseRoutes'

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
  const { courseSlug = DEFAULT_COURSE_SLUG, numero } = useParams()
  const n = Number(numero)
  const { data, isPending, error, refetch } = useLesson(courseSlug, n)
  const curriculum = useCourseCurriculum(courseSlug)

  if (!Number.isInteger(n)) return <p className="erro">Número de aula inválido.</p>
  if (isPending) return <Carregando oque={`a aula ${n}`} />
  if (error) return <Erro erro={error} aoTentarDeNovo={() => void refetch()} />
  const currentVersion = data.versions[0]
  const { previous, next } = adjacentLessons(curriculum.data, data.id)
  const courseTitle = curriculum.data?.course.title ?? courseSlug
  const unit = curriculum.data?.units.find((candidate) =>
    candidate.lessons.some((lesson) => lesson.id === data.id),
  )

  return (
    <>
      <p className="eyebrow">
        Aula {data.number} · {courseTitle}
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
          <Link className="btn" to={studyPath(courseSlug, data.number)}>
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
        <div className="practice-entry">
          <div>
            <p className="study-kicker">Uma questão por vez</p>
            <strong>
              {data.exercises.length} atividades com retomada, filtros e resumo final.
            </strong>
          </div>
          <Link className="btn" to={practicePath(courseSlug, data.number)}>
            Abrir laboratório
          </Link>
        </div>
      </Secao>

      <nav className="navbtns">
        {previous ? (
          <Link className="btn ghost" to={lessonPath(courseSlug, previous.number)}>
            ← Aula {previous.number}
          </Link>
        ) : (
          <Link
            className="btn ghost"
            to={unit ? unitPath(courseSlug, unit.slug) : coursePath(courseSlug)}
          >
            ← Mapa do curso
          </Link>
        )}
        {next ? (
          <Link className="btn ghost" to={lessonPath(courseSlug, next.number)}>
            Aula {next.number} →
          </Link>
        ) : (
          <Link className="btn ghost" to={coursePath(courseSlug)}>
            Concluir no mapa →
          </Link>
        )}
      </nav>
    </>
  )
}
