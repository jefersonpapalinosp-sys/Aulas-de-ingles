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

export function useLesson(number: number) {
  return useQuery({
    queryKey: ['lesson', number],
    queryFn: async () => {
      const { data, response } = await api.GET('/api/lessons/{number}', {
        params: { path: { number } },
      })
      if (!data) throw falhou(response?.status, `a aula ${number}`)
      return data
    },
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
