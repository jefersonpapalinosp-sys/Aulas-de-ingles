import type { LessonDetail } from '../../../api/client'
import { GrammarBlockView } from '../../../components/GrammarBlockView'
import { Markdown } from '../../../components/Markdown'

/** Teoria aplicada: o bloco de gramática da aula. */
export function EstudarStep({ lesson }: { lesson: LessonDetail }) {
  return (
    <div className="study-section">
      <p className="study-kicker">Teoria aplicada</p>
      <h2>{lesson.grammar_tag}</h2>
      {lesson.grammar_blocks.length > 0 ? (
        <div className="stack">
          {lesson.grammar_blocks.map((block) => (
            <GrammarBlockView bloco={block} key={block.heading} />
          ))}
        </div>
      ) : (
        <div className="media-fallback" role="note">
          <h3>Estudo textual alternativo</h3>
          <p>
            <strong>Contexto:</strong> <Markdown>{lesson.lead}</Markdown>
          </p>
          <p>
            Escreva duas frases sobre esse contexto usando <strong>{lesson.grammar_tag}</strong>
            {lesson.focus_points[0] && (
              <>
                {' '}e o foco <Markdown>{lesson.focus_points[0]}</Markdown>
              </>
            )}
            .
          </p>
        </div>
      )}
    </div>
  )
}
