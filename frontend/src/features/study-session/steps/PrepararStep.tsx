import type { LessonDetail } from '../../../api/client'
import { Markdown } from '../../../components/Markdown'

/** Aquecimento: o aluno responde antes de ver a aula. */
export function PrepararStep({ lesson }: { lesson: LessonDetail }) {
  return (
    <>
      <div className="study-intro-card">
        <p className="study-kicker">Antes de começar</p>
        <h2>O que você vai conseguir fazer</h2>
        {lesson.goals.length > 0 ? (
          <ul className="goals">
            {lesson.goals.map((goal) => (
              <li key={goal}>
                <Markdown>{goal}</Markdown>
              </li>
            ))}
          </ul>
        ) : (
          <p className="study-copy">Use o foco gramatical e o aquecimento como meta desta sessão.</p>
        )}
      </div>
      <aside className="study-prompt" aria-labelledby="study-warmup-title">
        <p className="study-kicker">Aquecimento · responda em voz alta</p>
        <h3 id="study-warmup-title">{lesson.warmup_prompt}</h3>
        <p>
          Tente usar uma frase curta em inglês. Não precisa acertar de primeira — volte a esta
          pergunta depois da prática.
        </p>
      </aside>
    </>
  )
}
