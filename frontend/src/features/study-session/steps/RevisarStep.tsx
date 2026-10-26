import type { LessonDetail } from '../../../api/client'
import { PronunciationList, VocabTable } from '../../../components/LessonSections'
import { Markdown } from '../../../components/Markdown'
import { ShadowingPractice } from '../../speaking/ShadowingPractice'
import { WritingWorkspace } from '../../writing/WritingWorkspace'

/** Consolidação: escrita, shadowing, pronúncia e vocabulário.
 *
 * É o único passo que pode ficar sem nenhum de seus blocos — existe aula sem
 * prompt de escrita, sem áudio com falas e sem vocabulário. A revisão textual
 * no fim é a saída para esse caso, em vez de uma tela vazia.
 */
export function RevisarStep({ lesson, userId }: { lesson: LessonDetail; userId: number }) {
  const shadowingMedia = lesson.media.find(
    (media) => media.kind === 'conversation_audio' && media.cues.length > 0,
  )
  const writingPrompt = lesson.writing_prompts[0]

  return (
    <>
      {writingPrompt && <WritingWorkspace prompt={writingPrompt} userId={userId} />}
      {shadowingMedia && (
        <ShadowingPractice
          courseSlug={lesson.course_slug}
          media={shadowingMedia}
          userId={userId}
          lessonNumber={lesson.number}
        />
      )}
      {lesson.pronunciation.length > 0 && (
        <div className="study-section">
          <p className="study-kicker">Consolidação</p>
          <h2>Revise o som e as palavras</h2>
          <p className="study-copy">
            Leia os termos em voz alta. Adicione ao deck os que você ainda não consegue recuperar
            sem olhar a tradução.
          </p>
          <PronunciationList notas={lesson.pronunciation} />
        </div>
      )}
      {lesson.vocab.length > 0 && (
        <div className="study-section">
          <h2>Vocabulário da aula</h2>
          <VocabTable itens={lesson.vocab} />
        </div>
      )}
      {!writingPrompt && !shadowingMedia && lesson.pronunciation.length === 0 && lesson.vocab.length === 0 && (
        <div className="media-fallback" role="note">
          <h2>Revisão textual rápida</h2>
          <ol>
            <li>
              Resuma em uma frase: <Markdown>{lesson.lead}</Markdown>
            </li>
            <li>Crie um novo exemplo com {lesson.grammar_tag}.</li>
            <li>Responda novamente ao aquecimento: {lesson.warmup_prompt}</li>
          </ol>
        </div>
      )}
    </>
  )
}
