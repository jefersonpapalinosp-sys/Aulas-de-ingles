import { useEffect, useMemo, useState } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { useSessao } from '../api/auth'
import type { LessonDetail } from '../api/client'
import { useMarcarEstudada, useSalvarStudySession, useStudySession } from '../api/progress'
import { useLesson } from '../api/queries'
import { ExerciseCard } from '../components/ExerciseCard'
import { GrammarBlockView } from '../components/GrammarBlockView'
import { PhraseList, PronunciationList, VocabTable } from '../components/LessonSections'
import { Markdown } from '../components/Markdown'
import { Carregando, Erro } from '../components/States'
import { StepNavigator } from '../features/study-session/StepNavigator'
import { LessonAudioPlayer } from '../features/media/LessonAudioPlayer'
import { ShadowingPractice } from '../features/speaking/ShadowingPractice'
import { WritingWorkspace } from '../features/writing/WritingWorkspace'
import {
  isStudyStep,
  loadStudyProgress,
  saveStudyProgress,
  STUDY_STEPS,
  type StudyStepSlug,
} from '../features/study-session/studyProgress'

const WARMUP_BY_LESSON: Record<number, string> = {
  31: 'Como você compararia duas formas de transporte?',
  32: 'Como você pediria uma informação e responderia com entusiasmo?',
  33: 'Como você explicaria, em ordem, as regras de um esporte?',
  34: 'Como você falaria sobre um plano futuro que ainda não é certo?',
  35: 'Como você pediria quantidades e embalagens em uma lista de compras?',
  36: 'Como você diria onde estão os ingredientes e se ofereceria para ajudar?',
  37: 'Como você concordaria ou discordaria de uma opinião com educação?',
  38: 'Como você descreveria seu melhor amigo usando superlativos?',
  39: 'Como você explicaria que um produto não cumpriu o que prometeu?',
  40: 'Como você pediria para alguém falar mais alto ou andar mais devagar?',
}

const LISTENING_FOCUS_BY_LESSON: Record<number, string> = {
  31: 'os transportes comparados e o conselho final',
  32: 'quem recebe cada pergunta ou resposta e as interjeições',
  33: 'os marcadores de sequência e quem realiza cada ação no beisebol',
  34: 'a diferença de certeza entre *might* e *will*',
  35: 'as embalagens, quantidades e a lista de compras errada',
  36: 'as preposições de lugar e as decisões com *I’ll*',
  37: 'os possessivos e as frases usadas para concordar ou discordar',
  38: 'os superlativos empregados para descrever cada amigo',
  39: 'os prefixos negativos e as pistas que revelam o problema do produto',
  40: 'os advérbios que mudam a maneira e o momento de cada ação',
}

function StepContent({
  lesson,
  step,
  userId,
}: {
  lesson: LessonDetail
  step: StudyStepSlug
  userId: number
}) {
  if (step === 'preparar') {
    return (
      <>
        <div className="study-intro-card">
          <p className="study-kicker">Antes de começar</p>
          <h2>O que você vai conseguir fazer</h2>
          <ul className="goals">
            {lesson.goals.map((goal) => (
              <li key={goal}>
                <Markdown>{goal}</Markdown>
              </li>
            ))}
          </ul>
        </div>
        <aside className="study-prompt" aria-labelledby="study-warmup-title">
          <p className="study-kicker">Aquecimento · responda em voz alta</p>
          <h3 id="study-warmup-title">{WARMUP_BY_LESSON[lesson.number]}</h3>
          <p>
            Tente usar uma frase curta em inglês. Não precisa acertar de primeira — volte a esta
            pergunta depois da prática.
          </p>
        </aside>
      </>
    )
  }

  if (step === 'assistir') {
    const conversationAudio = lesson.media.find((media) => media.kind === 'conversation_audio')
    const listeningExercises = lesson.exercises.filter((exercise) => exercise.skill === 'listening')
    return (
      <>
        {conversationAudio && (
          <LessonAudioPlayer
            media={conversationAudio}
            userId={userId}
            sourcePageUrl={lesson.voa_url}
          />
        )}
        {listeningExercises.length > 0 && (
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
            Estratégia · {lesson.versions[0]?.learning_strategy ?? 'escuta ativa'}
          </p>
          <h2>Escute primeiro pelo contexto</h2>
          <ol>
            <li>Na primeira vez, não pause: identifique as pessoas, o lugar e o problema.</li>
            <li>
              Na segunda, concentre-se em {LISTENING_FOCUS_BY_LESSON[lesson.number]}.
            </li>
            <li>Depois, abra os trechos selecionados e confira o que conseguiu reconhecer.</li>
          </ol>
          <a className="watch" href={lesson.voa_url} target="_blank" rel="noopener noreferrer">
            Abrir vídeo e áudio na VOA ↗
          </a>
        </div>
        <div className="study-section">
          <h2>Frases para acompanhar</h2>
          <PhraseList frases={lesson.phrases} />
        </div>
      </>
    )
  }

  if (step === 'estudar') {
    return (
      <div className="study-section">
        <p className="study-kicker">Teoria aplicada</p>
        <h2>{lesson.grammar_tag}</h2>
        <div className="stack">
          {lesson.grammar_blocks.map((block) => (
            <GrammarBlockView bloco={block} key={block.heading} />
          ))}
        </div>
      </div>
    )
  }

  if (step === 'praticar') {
    return (
      <div className="study-section">
        <p className="study-kicker">Recuperação ativa</p>
        <h2>Agora produza as respostas</h2>
        <p className="study-copy">
          Responda antes de pedir o gabarito. A correção acontece no servidor e cada tentativa
          fica registrada no seu progresso.
        </p>
        <div className="stack tight">
          {lesson.exercises
            .filter((exercise) => exercise.skill !== 'listening')
            .map((exercise, index) => (
              <ExerciseCard
                exercicio={exercise}
                numero={index + 1}
                userId={userId}
                key={exercise.id}
              />
            ))}
        </div>
      </div>
    )
  }

  const shadowingMedia = lesson.media.find(
    (media) => media.kind === 'conversation_audio' && media.cues.length > 0,
  )
  const writingPrompt = lesson.writing_prompts[0]

  return (
    <>
      {writingPrompt && <WritingWorkspace prompt={writingPrompt} userId={userId} />}
      {shadowingMedia && (
        <ShadowingPractice
          media={shadowingMedia}
          userId={userId}
          lessonNumber={lesson.number}
        />
      )}
      <div className="study-section">
        <p className="study-kicker">Consolidação</p>
        <h2>Revise o som e as palavras</h2>
        <p className="study-copy">
          Leia os termos em voz alta. Adicione ao deck os que você ainda não consegue recuperar
          sem olhar a tradução.
        </p>
        <PronunciationList notas={lesson.pronunciation} />
      </div>
      <div className="study-section">
        <h2>Vocabulário da aula</h2>
        <VocabTable itens={lesson.vocab} />
      </div>
    </>
  )
}

export function StudyPage() {
  const { numero, etapa } = useParams()
  const lessonNumber = Number(numero)
  const navigate = useNavigate()
  const { usuario } = useSessao()
  const { data: lesson, isPending, error, refetch } = useLesson(lessonNumber)
  const marcarEstudada = useMarcarEstudada()
  const serverSession = useStudySession(
    lessonNumber,
    Boolean(usuario) && Number.isInteger(lessonNumber),
  )
  const {
    mutate: sincronizarSessao,
    isPending: sincronizando,
    isError: sincronizacaoFalhou,
    isSuccess: sincronizado,
  } = useSalvarStudySession(lessonNumber)
  const stored = useMemo(
    () => loadStudyProgress(usuario?.id ?? 0, lessonNumber),
    [usuario?.id, lessonNumber],
  )
  const [completedSteps, setCompletedSteps] = useState<StudyStepSlug[]>(stored.completedSteps)
  const [resumeStep, setResumeStep] = useState<StudyStepSlug>(stored.currentStep)
  const [hydrated, setHydrated] = useState(false)

  useEffect(() => {
    setCompletedSteps(stored.completedSteps)
    setResumeStep(stored.currentStep)
    setHydrated(false)
  }, [stored])

  useEffect(() => {
    if (!usuario || serverSession.isPending || hydrated) return
    const remoto = serverSession.data?.updated_at ? serverSession.data : null
    const localMaisCompleto =
      remoto !== null && stored.completedSteps.length > remoto.completed_steps.length
    setCompletedSteps(
      localMaisCompleto || !remoto ? stored.completedSteps : remoto.completed_steps,
    )
    setResumeStep(localMaisCompleto || !remoto ? stored.currentStep : remoto.current_step)
    setHydrated(true)
  }, [usuario, serverSession.isPending, serverSession.data, stored, hydrated])

  useEffect(() => {
    if (!usuario || !hydrated || !Number.isInteger(lessonNumber) || !isStudyStep(etapa)) return
    saveStudyProgress(usuario.id, lessonNumber, {
      currentStep: etapa,
      completedSteps,
    })
    sincronizarSessao({ current_step: etapa, completed_steps: completedSteps })
  }, [usuario, hydrated, lessonNumber, etapa, completedSteps, sincronizarSessao])

  if (!Number.isInteger(lessonNumber)) return <p className="erro">Número de aula inválido.</p>
  if (!usuario) return null
  if (!etapa) {
    if (serverSession.isPending || !hydrated) return <Carregando oque="seu ponto de retomada" />
    return <Navigate to={`/aulas/${lessonNumber}/estudar/${resumeStep}`} replace />
  }
  if (!isStudyStep(etapa)) {
    return (
      <div className="estado-erro" role="alert">
        <p>Esta etapa de estudo não existe.</p>
        <Link className="btn ghost" to={`/aulas/${lessonNumber}/estudar`}>
          Retomar a aula
        </Link>
      </div>
    )
  }
  if (isPending || serverSession.isPending || !hydrated) {
    return <Carregando oque={`a aula ${lessonNumber}`} />
  }
  if (error) return <Erro erro={error} aoTentarDeNovo={() => void refetch()} />

  const currentStep: StudyStepSlug = etapa
  const userId = usuario.id
  const stepIndex = STUDY_STEPS.findIndex((step) => step.slug === currentStep)
  const previous = STUDY_STEPS[stepIndex - 1]
  const next = STUDY_STEPS[stepIndex + 1]
  const isComplete = STUDY_STEPS.every((step) => completedSteps.includes(step.slug))

  function persist(currentStep: StudyStepSlug, completed: StudyStepSlug[]) {
    saveStudyProgress(userId, lessonNumber, {
      currentStep,
      completedSteps: completed,
    })
  }

  function completeAndContinue() {
    const completed = completedSteps.includes(currentStep)
      ? completedSteps
      : [...completedSteps, currentStep]
    setCompletedSteps(completed)

    if (next) {
      persist(next.slug, completed)
      navigate(`/aulas/${lessonNumber}/estudar/${next.slug}`)
      window.scrollTo({ top: 0, behavior: 'smooth' })
      return
    }

    persist(currentStep, completed)
    marcarEstudada.mutate({ numero: lessonNumber, estudada: true })
  }

  function goBack() {
    if (!previous) return
    persist(previous.slug, completedSteps)
    navigate(`/aulas/${lessonNumber}/estudar/${previous.slug}`)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <article className="study-workspace">
      <header className="study-header">
        <div>
          <p className="eyebrow">Aula {lesson.number} · estudo guiado</p>
          <h1>{lesson.title}</h1>
          <p className="lead">
            <em>{lesson.title_pt}</em> · {lesson.grammar_tag}
          </p>
        </div>
        <Link className="study-overview-link" to={`/aulas/${lesson.number}`}>
          Ver aula completa
        </Link>
      </header>

      <div
        className="study-progress"
        role="progressbar"
        aria-label="Progresso da jornada"
        aria-valuemin={0}
        aria-valuemax={STUDY_STEPS.length}
        aria-valuenow={completedSteps.length}
      >
        <span style={{ width: `${(completedSteps.length / STUDY_STEPS.length) * 100}%` }} />
      </div>

      <StepNavigator
        lessonNumber={lessonNumber}
        currentStep={currentStep}
        completedSteps={completedSteps}
      />

      <div className="study-body">
        <p className="study-step-label">
          Etapa {stepIndex + 1} de {STUDY_STEPS.length}
        </p>
        <StepContent lesson={lesson} step={currentStep} userId={userId} />

        {isComplete && currentStep === 'revisar' && (
          <div className="study-finished" role="status">
            <p className="study-kicker">Jornada concluída</p>
            <h2>Boa! Você percorreu as cinco etapas da Aula {lesson.number}.</h2>
            <p>
              {marcarEstudada.isPending
                ? 'Salvando a conclusão…'
                : marcarEstudada.isError
                  ? 'A jornada foi salva neste navegador, mas não foi possível marcar a aula no servidor. Tente novamente.'
                  : 'A aula foi marcada como estudada e as palavras do deck voltarão na fila de revisão.'}
            </p>
          </div>
        )}
      </div>

      <footer className="study-actions">
        {previous ? (
          <button type="button" className="btn ghost" onClick={goBack}>
            ← {previous.shortTitle}
          </button>
        ) : (
          <Link className="btn ghost" to={`/aulas/${lesson.number}`}>
            ← Sair da jornada
          </Link>
        )}
        <span className={`study-sync ${sincronizacaoFalhou ? 'failed' : ''}`} aria-live="polite">
          {sincronizando
            ? 'Sincronizando…'
            : sincronizacaoFalhou
              ? 'Salvo neste dispositivo; sincronização pendente.'
              : sincronizado
                ? 'Progresso sincronizado.'
                : ''}
        </span>
        <button
          type="button"
          className="btn"
          onClick={completeAndContinue}
          disabled={marcarEstudada.isPending || (isComplete && !next && !marcarEstudada.isError)}
        >
          {next
            ? `Concluir e ir para ${next.shortTitle}`
            : isComplete && marcarEstudada.isError
              ? 'Tentar marcar novamente'
              : isComplete
                ? 'Concluída'
                : 'Concluir aula'}
        </button>
      </footer>
    </article>
  )
}
