import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, type Exercise, type ExerciseHint } from '../../api/client'
import { invalidateStudy } from '../../api/invalidateStudy'
import { queueAttempt } from '../offline/attemptQueue'
import type { ExerciseActivityEvent } from '../practice/types'
import type { Veredito } from './ExerciseVerdict'

/** As três ações de uma atividade objetiva: conferir, pedir dica e revelar.
 *
 * A correção é do servidor. A resposta certa não faz parte do contrato de
 * leitura, então mandá-la ao navegador para o JavaScript comparar seria
 * publicar o gabarito; "Resposta" o pede explicitamente, e isso fica no
 * histórico do aluno.
 */
export function useExerciseActions({
  exercicio, userId, practiceSessionId, courseSlug, lessonNumber,
  onVerdict, onHint, onWrong, onAnswered, onActivity,
}: {
  exercicio: Exercise
  userId: number
  practiceSessionId?: number
  courseSlug?: string
  lessonNumber?: number
  onVerdict: (veredito: Veredito) => void
  onHint: (hint: ExerciseHint) => void
  onWrong: () => void
  onAnswered?: (acertou: boolean) => void
  onActivity?: (event: ExerciseActivityEvent) => void
}) {
  const qc = useQueryClient()

  function saveForLater(answer: string, key: string) {
    return queueAttempt({
      userId,
      exerciseId: exercicio.id,
      answer,
      idempotencyKey: key,
      createdAt: new Date().toISOString(),
      sessionId: practiceSessionId,
      courseSlug,
      lessonNumber,
    })
  }

  async function hintFor(level: number): Promise<ExerciseHint> {
    const recusa = (status?: number) => new Error(status === 409
      ? 'Faça uma tentativa antes de abrir a próxima dica.'
      : `A API respondeu ${status ?? 'nada'} ao buscar a dica.`)
    if (practiceSessionId !== undefined) {
      const { data, response } = await api.POST(
        '/api/practice-sessions/{session_id}/items/{exercise_id}/hints/{level}',
        { params: { path: { session_id: practiceSessionId, exercise_id: exercicio.id, level } } },
      )
      if (!data) throw recusa(response?.status)
      return { level: data.level, content: data.content }
    }
    const { data, response } = await api.GET('/api/exercises/{exercise_id}/hints/{level}', {
      params: { path: { exercise_id: exercicio.id, level } },
    })
    if (!data) throw recusa(response?.status)
    return data
  }

  const conferir = useMutation({
    // A própria mutationFn decide entre API e fila local. Sem `always`, o
    // TanStack pausa a mutation ao receber o evento offline e esse fallback
    // nunca é executado.
    networkMode: 'always',
    mutationFn: async ({ answer, key }: { answer: string; key: string }) => {
      if (!navigator.onLine) {
        await saveForLater(answer, key)
        return { data: null, key }
      }
      let result
      try {
        result = await api.POST('/api/exercises/{exercise_id}/attempt', {
          params: { path: { exercise_id: exercicio.id } },
          body: {
            answer,
            idempotency_key: key,
            ...(practiceSessionId === undefined ? {} : { practice_session_id: practiceSessionId }),
          },
        })
      } catch (error) {
        // fetch rejeita com TypeError quando a conexão cai entre o precheck e
        // a resposta. Erros HTTP chegam normalmente em `response` abaixo e
        // não devem entrar na fila offline.
        if (error instanceof TypeError
          || (error instanceof DOMException && error.name === 'NetworkError')) {
          await saveForLater(answer, key)
          return { data: null, key }
        }
        throw error
      }
      const { data, response } = result
      if (!data && !response) {
        await saveForLater(answer, key)
        return { data: null, key }
      }
      if (!data) throw new Error(`A API respondeu ${response?.status ?? 'nada'} ao conferir.`)
      return { data, key }
    },
    onSuccess: ({ data, key }) => {
      if (!data) {
        onVerdict({ tipo: 'fila' })
        onActivity?.({ type: 'attempt', exerciseId: exercicio.id, status: 'queued',
          idempotencyKey: key, correct: null })
        return
      }
      onVerdict(data.correct
        ? { tipo: 'certo', explicacao: data.explanation }
        : { tipo: 'errado', feedback: data.feedback })
      if (!data.correct) onWrong()
      onAnswered?.(data.correct)
      onActivity?.({ type: 'attempt', exerciseId: exercicio.id,
        status: data.correct ? 'correct' : 'incorrect', idempotencyKey: key, correct: data.correct })
      // Errar pode ter semeado o deck; acertar move competências e a jornada da aula.
      void invalidateStudy(qc, 'attempt')
    },
    onError: (error: Error) => onVerdict({ tipo: 'falhou', mensagem: error.message }),
  })

  const pedirDica = useMutation({
    mutationFn: async (level: number) => ({ hint: await hintFor(level), level }),
    onSuccess: ({ hint, level }) => {
      onHint(hint)
      onActivity?.({ type: 'hint', exerciseId: exercicio.id, level })
    },
  })

  const revelar = useMutation({
    mutationFn: async () => {
      if (practiceSessionId !== undefined) {
        const { data, response } = await api.POST(
          '/api/practice-sessions/{session_id}/items/{exercise_id}/reveal',
          { params: { path: { session_id: practiceSessionId, exercise_id: exercicio.id } } },
        )
        if (!data) throw new Error(`A API respondeu ${response?.status ?? 'nada'} ao buscar.`)
        return data
      }
      const { data, response } = await api.GET('/api/exercises/{exercise_id}/answer', {
        params: { path: { exercise_id: exercicio.id } },
      })
      if (!data) throw new Error(`A API respondeu ${response?.status ?? 'nada'} ao buscar.`)
      return data
    },
    onSuccess: (revelado) => {
      onVerdict({ tipo: 'revelado', respostas: revelado.answers, explicacao: revelado.explanation })
      onActivity?.({ type: 'reveal', exerciseId: exercicio.id })
    },
    onError: (error: Error) => onVerdict({ tipo: 'falhou', mensagem: error.message }),
  })

  return { conferir, pedirDica, revelar,
    ocupado: conferir.isPending || revelar.isPending || pedirDica.isPending }
}
