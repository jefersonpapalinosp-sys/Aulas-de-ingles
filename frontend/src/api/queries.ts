import { useQuery } from '@tanstack/react-query'
import { api } from './client'
import { ApiError } from './errors'

/** Mensagem de erro que o usuário consegue agir em cima. */
const falhou = (response: Response | undefined, oque: string): Error => new ApiError(oque, response)

export function useLessons() {
  return useQuery({
    queryKey: ['lessons'],
    queryFn: async () => {
      const { data, response } = await api.GET('/api/lessons')
      if (!data) throw falhou(response, 'a lista de aulas')
      return data
    },
  })
}

export function useCourses() {
  return useQuery({
    queryKey: ['courses'],
    queryFn: async () => {
      const { data, response } = await api.GET('/api/courses')
      if (!data) throw falhou(response, 'o catálogo de cursos')
      return data
    },
  })
}

export function useCourseCurriculum(courseSlug: string, enabled = true) {
  return useQuery({
    queryKey: ['course-curriculum', courseSlug],
    queryFn: async () => {
      const { data, response } = await api.GET('/api/courses/{course_slug}/curriculum', {
        params: { path: { course_slug: courseSlug } },
      })
      if (!data) throw falhou(response, `o currículo de ${courseSlug}`)
      return data
    },
    enabled: enabled && Boolean(courseSlug),
  })
}

export function useLesson(courseSlug: string, number: number) {
  return useQuery({
    queryKey: ['lesson', courseSlug, number],
    queryFn: async () => {
      const { data, response } = await api.GET(
        '/api/courses/{course_slug}/lessons/{number}',
        {
          params: { path: { course_slug: courseSlug, number } },
        },
      )
      if (!data) throw falhou(response, `a aula ${number}`)
      return data
    },
    enabled: Boolean(courseSlug) && Number.isInteger(number),
  })
}

export function useAllExercises(courseSlug?: string, unitSlug?: string) {
  return useQuery({
    queryKey: ['exercises', courseSlug ?? 'all', unitSlug ?? 'all'],
    queryFn: async () => {
      const { data, response } = await api.GET('/api/exercises', {
        params: {
          query: {
            course: courseSlug,
            unit: unitSlug,
          },
        },
      })
      if (!data) throw falhou(response, 'os exercícios do bloco')
      return data
    },
  })
}

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: async () => {
      const { data, response } = await api.GET('/api/health')
      if (!data) throw falhou(response, 'o estado da API')
      return data
    },
    retry: false,
  })
}
