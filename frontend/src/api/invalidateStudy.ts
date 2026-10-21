import type { QueryClient } from '@tanstack/react-query'

/** Projeções pessoais que qualquer resultado de estudo pode mover, inclusive a última revisão. */
const personal = ['review', 'progress', 'today', 'skills', 'course-completion', 'writing-history'] as const

/**
 * Único mapa evento → prefixos de chave do cache. Nenhum componente ou hook
 * chama `invalidateQueries` diretamente: todos nomeiam o evento que aconteceu e
 * este arquivo decide o que fica velho. Prefixos invalidam todas as variações
 * (`['course-completion', slug]`, `['study-session', slug, numero]`, …).
 *
 * Lista vazia significa "o cache inteiro" — usada só quando a sessão é
 * reconfirmada na mesma conta e qualquer dado pode ter mudado em outro dispositivo.
 */
export const STUDY_INVALIDATIONS = {
  /** Tentativa de exercício corrigida online: trilha, deck, Hoje, competências e a jornada da aula. */
  attempt: ['progress', 'review', 'today', 'skills', 'study-session', 'course-completion'],
  /** Fila offline sincronizada: o mesmo que `attempt`, mais as sessões de prática que ela alimenta. */
  queueSync: ['progress', 'review', 'today', 'skills', 'study-session', 'course-completion',
    'practice-session', 'practice-session-active'],
  /** Jornada da aula salva com revisão confirmada. */
  studySession: personal,
  /** A API recusou a jornada: reler a revisão da conta antes de tentar de novo. */
  studySessionRejected: ['study-session'],
  /** Aula marcada ou desmarcada como estudada. */
  studied: ['progress', 'today', 'course-completion'],
  /** Nota SM-2 confirmada com recibo. */
  reviewGrade: personal,
  /** Item do deck suspenso, reativado ou excluído. */
  reviewItemChange: ['review', 'progress', 'today'],
  /** Vocabulário acrescentado ao deck. */
  reviewItemAdded: ['review', 'progress'],
  /** Checkpoint de unidade respondido. */
  courseReviewAttempt: ['course-review', 'course-completion', 'today'],
  /** Texto analisado (determinístico ou assistido). */
  writingFeedback: personal,
  /** Qualquer uso ou reserva de cota assistida, inclusive falhas. */
  assistUsage: ['assist-status'],
  /** Gravação de voz salva na conta. */
  speakingUpload: ['speaking-attempts', 'course-completion'],
  /** Gravação excluída; pode liberar cota de transcrição. */
  speakingDelete: ['speaking-attempts', 'course-completion', 'assist-status'],
  /** Transcrição solicitada ou excluída. */
  transcriptionChange: ['speaking-attempts', 'assist-status'],
  /** Avaliação humana de uma transcrição. */
  transcriptionRating: ['speaking-attempts'],
  /** Plano de estudo salvo. */
  studyPlan: ['today'],
  /** Tempo ativo creditado pela API. */
  activityCredited: ['today'],
  /** Sessão reconfirmada na mesma conta: tudo em cache pode ter mudado. */
  sessionConfirmed: [],
} as const satisfies Record<string, readonly string[]>

export type StudyEvent = keyof typeof STUDY_INVALIDATIONS

export async function invalidateStudy(client: QueryClient, event: StudyEvent): Promise<void> {
  const keys = STUDY_INVALIDATIONS[event]
  if (keys.length === 0) {
    await client.invalidateQueries()
    return
  }
  await Promise.all(keys.map((key) => client.invalidateQueries({ queryKey: [key] })))
}
