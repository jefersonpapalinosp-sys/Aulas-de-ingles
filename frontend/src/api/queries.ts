import { useQuery } from '@tanstack/react-query'
import { api } from './client'

/** Mensagem de erro que o usuário consegue agir em cima. */
function falhou(status: number | undefined, oque: string): Error {
  if (status === 404) return new Error(`${oque} não existe.`)
  if (status === undefined) return new Error(`Não foi possível falar com a API para buscar ${oque}.`)
  return new Error(`A API respondeu ${status} ao buscar ${oque}.`)
}

export function useLessons() {
  return useQuery({
    queryKey: ['lessons'],
    queryFn: async () => {
      const { data, response } = await api.GET('/api/lessons')
      if (!data) throw falhou(response?.status, 'a lista de aulas')
      return data
    },
  })
}

export function useCourses() {
  return useQuery({
    queryKey: ['courses'],
    queryFn: async () => {
      const { data, response } = await api.GET('/api/courses')
      if (!data) throw falhou(response?.status, 'o catálogo de cursos')
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
      if (!data) throw falhou(response?.status, `o currículo de ${courseSlug}`)
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
      if (!data) throw falhou(response?.status, `a aula ${number}`)
      return data
    },
    enabled: Boolean(courseSlug) && Number.isInteger(number),
  })
}

export function useAllExercises() {
  return useQuery({
    queryKey: ['exercises'],
    queryFn: async () => {
      const { data, response } = await api.GET('/api/exercises')
      if (!data) throw falhou(response?.status, 'os exercícios do bloco')
      return data
    },
  })
}

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: async () => {
      const { data, response } = await api.GET('/api/health')
      if (!data) throw falhou(response?.status, 'o estado da API')
      return data
    },
    retry: false,
  })
}
