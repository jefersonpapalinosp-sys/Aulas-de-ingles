import type { LessonDetail } from '../../../api/client'
import { PracticeRunner } from '../../practice/PracticeRunner'

/** Recuperação ativa: produzir a resposta antes de pedir o gabarito. */
export function PraticarStep({ lesson, userId }: { lesson: LessonDetail; userId: number }) {
  return (
    <div className="study-section">
      <p className="study-kicker">Recuperação ativa</p>
      <h2>Agora produza as respostas</h2>
      <p className="study-copy">
        Responda antes de pedir o gabarito. A correção acontece no servidor e cada tentativa
        fica registrada no seu progresso.
      </p>
      {lesson.exercises.length > 0 ? (
        <PracticeRunner
          key={`${lesson.course_slug}:${lesson.number}`}
          courseSlug={lesson.course_slug}
          lessonNumber={lesson.number}
          lessonTitle={lesson.title}
          userId={userId}
          variant="embedded"
          initialFilters={{ skill: 'grammar' }}
          lockFilters
        />
      ) : (
        <div className="media-fallback" role="note">
          <h3>Prática textual alternativa</h3>
          <ol>
            <li>Responda em inglês: {lesson.warmup_prompt}</li>
            <li>Reescreva sua resposta usando {lesson.grammar_tag}.</li>
            <li>Leia as duas versões em voz alta e escolha a mais clara.</li>
          </ol>
        </div>
      )}
    </div>
  )
}
