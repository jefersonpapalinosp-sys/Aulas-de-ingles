import type { LessonDetail } from '../../../api/client'
import { ExerciseCard } from '../../../components/ExerciseCard'
import { PhraseList } from '../../../components/LessonSections'
import { Markdown } from '../../../components/Markdown'
import { LessonAudioPlayer } from '../../media/LessonAudioPlayer'

/** Escuta: o áudio da conversa e os exercícios de listening. */
export function AssistirStep({ lesson, userId }: { lesson: LessonDetail; userId: number }) {
  const conversationAudio = lesson.media.find((media) => media.kind === 'conversation_audio')
  const listeningExercises = lesson.exercises.filter((exercise) => exercise.skill === 'listening')
  return (
    <>
      {conversationAudio ? (
        <LessonAudioPlayer
          media={conversationAudio}
          userId={userId}
          sourcePageUrl={lesson.voa_url}
        />
      ) : (
        <div className="media-fallback" role="note">
          <p className="study-kicker">Alternativa textual</p>
          <h2>Áudio não disponível neste aplicativo</h2>
          <p>
            <strong>Resumo:</strong> <Markdown>{lesson.lead}</Markdown>
          </p>
          <p>
            <strong>Foco de compreensão:</strong>{' '}
            {lesson.listening_focus || lesson.grammar_tag}.
          </p>
          <ol>
            <li>Leia o resumo uma vez para identificar situação, pessoas e objetivo.</li>
            <li>Escreva duas palavras que você esperaria ouvir nessa situação.</li>
            <li>Crie uma frase curta em inglês usando o foco indicado acima.</li>
          </ol>
          <a href={lesson.voa_url} target="_blank" rel="noopener noreferrer">
            Abrir a aula na VOA ↗
          </a>
        </div>
      )}
      {conversationAudio && listeningExercises.length > 0 && (
        <div className="study-section listening-check">
          <p className="study-kicker">Compreensão geral</p>
          <h2>Escute e responda antes de ler</h2>
          <p className="study-copy">
            Faça uma primeira escuta sem abrir a transcrição. Depois confira os trechos e tente
            novamente se precisar.
          </p>
          <div className="stack tight">
            {listeningExercises.map((exercise, index) => (
              <ExerciseCard
                exercicio={exercise}
                numero={index + 1}
                userId={userId}
                key={exercise.id}
              />
            ))}
          </div>
        </div>
      )}
      <div className="study-instructions">
        <p className="study-kicker">
          Estratégia ·{' '}
          {conversationAudio
            ? (lesson.versions[0]?.learning_strategy ?? 'escuta ativa')
            : 'leitura contextual'}
        </p>
        <h2>{conversationAudio ? 'Escute primeiro pelo contexto' : 'Leia primeiro pelo contexto'}</h2>
        {conversationAudio ? (
          <>
            <ol>
              <li>Na primeira vez, não pause: identifique as pessoas, o lugar e o problema.</li>
              <li>
                Na segunda, concentre-se em {lesson.listening_focus}.
              </li>
              <li>Depois, abra os trechos selecionados e confira o que conseguiu reconhecer.</li>
            </ol>
            <a className="watch" href={lesson.voa_url} target="_blank" rel="noopener noreferrer">
              Abrir vídeo e áudio na VOA ↗
            </a>
          </>
        ) : (
          <ol>
            <li>Explique com suas palavras qual é a situação apresentada no resumo.</li>
            <li>Compare sua frase em inglês com o foco gramatical: {lesson.grammar_tag}.</li>
            <li>Leia a frase em voz alta e ajuste uma palavra para criar uma nova versão.</li>
          </ol>
        )}
      </div>
      {lesson.phrases.length > 0 && (
        <div className="study-section">
          <h2>Frases para acompanhar</h2>
          <PhraseList frases={lesson.phrases} />
        </div>
      )}
    </>
  )
}
