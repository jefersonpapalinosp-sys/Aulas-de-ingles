import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type Exercise } from './client'
import type {
  CreatePracticeSessionInput,
  PracticeFilters,
  PracticeSession,
} from '../features/practice/types'

function queryFilters(filters: PracticeFilters) {
  return {
    activity_type: filters.activityType,
    skill: filters.skill,
    objective: filters.objective,
  }
}

function practiceError(status: number | undefined, action: string): Error {
  if (status === 404) return new Error('A aula ou a sessão de exercícios não existe mais.')
  if (status === 409) {
    return new Error(
      'Já existe uma sessão com outra configuração. Retome-a antes de iniciar uma nova.',
    )
  }
  if (status === undefined) {
    return new Error(`Sem conexão para ${action}. Confira a rede e tente novamente.`)
  }
  return new Error(`A API respondeu ${status} ao ${action}.`)
}

export function usePracticeExercises(
  courseSlug: string,
  lessonNumber: number,
  filters: PracticeFilters = {},
  enabled = true,
) {
  return useQuery({
    queryKey: [
      'practice-exercises',
      courseSlug,
      lessonNumber,
      filters.activityType ?? 'all',
      filters.skill ?? 'all',
      filters.objective ?? 'all',
    ],
    queryFn: async () => {
      const { data, response } = await api.GET(
        '/api/courses/{course_slug}/lessons/{number}/exercises',
        {
          params: {
            path: { course_slug: courseSlug, number: lessonNumber },
            query: queryFilters(filters),
          },
        },
      )
      if (!data) throw practiceError(response?.status, 'buscar os exercícios')
      return data as Exercise[]
    },
    enabled: enabled && Boolean(courseSlug) && Number.isInteger(lessonNumber),
  })
}

export function useActivePracticeSession(
  courseSlug: string,
  lessonNumber: number,
  enabled = true,
) {
  return useQuery({
    queryKey: ['practice-session-active', courseSlug, lessonNumber],
    queryFn: async () => {
      const { data, response } = await api.GET(
        '/api/courses/{course_slug}/lessons/{number}/practice-sessions/active',
        { params: { path: { course_slug: courseSlug, number: lessonNumber } } },
      )
      if (response?.status === 204) return null
      if (!data) throw practiceError(response?.status, 'buscar sua sessão de exercícios')
      return data as PracticeSession
    },
    enabled: enabled && Boolean(courseSlug) && Number.isInteger(lessonNumber),
    staleTime: 0,
  })
}

export function usePracticeSession(sessionId: number | null, enabled = true) {
  return useQuery({
    queryKey: ['practice-session', sessionId],
    queryFn: async () => {
      const { data, response } = await api.GET('/api/practice-sessions/{session_id}', {
        params: { path: { session_id: sessionId ?? 0 } },
      })
      if (!data) throw practiceError(response?.status, 'buscar sua sessão de exercícios')
      return data as PracticeSession
    },
    enabled: enabled && sessionId !== null,
    staleTime: 0,
  })
}

export function useCreatePracticeSession(courseSlug: string, lessonNumber: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: CreatePracticeSessionInput) => {
      const { data, response } = await api.POST(
        '/api/courses/{course_slug}/lessons/{number}/practice-sessions',
        {
          params: { path: { course_slug: courseSlug, number: lessonNumber } },
          body,
        },
      )
      if (!data) throw practiceError(response?.status, 'iniciar a prática')
      return data as PracticeSession
    },
    onSuccess: (session) => {
      qc.setQueryData(['practice-session-active', courseSlug, lessonNumber], session)
      qc.setQueryData(['practice-session', session.id], session)
    },
  })
}

export function useUpdatePracticePosition() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      sessionId,
      currentPosition,
      expectedRevision,
      idempotencyKey,
    }: {
      sessionId: number
      currentPosition: number
      expectedRevision: number
      idempotencyKey: string
    }) => {
      const { data, response } = await api.PUT(
        '/api/practice-sessions/{session_id}/position',
        {
          params: { path: { session_id: sessionId } },
          body: {
            current_position: currentPosition,
            expected_revision: expectedRevision,
            idempotency_key: idempotencyKey,
          },
        },
      )
      if (!data) throw practiceError(response?.status, 'salvar a posição da prática')
      return data as PracticeSession
    },
    onSuccess: (session) => {
      qc.setQueryData(['practice-session', session.id], session)
      qc.setQueryData(
        ['practice-session-active', session.course_slug, session.lesson_number],
        session,
      )
    },
  })
}
