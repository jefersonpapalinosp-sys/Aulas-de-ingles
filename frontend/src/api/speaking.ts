import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api, authenticatedFetch, type SpeakingAttempt } from './client'
import { invalidateStudy } from './invalidateStudy'

/** Gravações salvas da aula e as ações sobre elas.
 *
 * Fica junto porque são a mesma coisa do ponto de vista do aluno: a lista do
 * que ele já gravou e o que ele pode fazer com cada item. Cada ação devolve a
 * fala para a linha de status da tela, em vez de manter uma segunda — duas
 * linhas de status competindo escondem a mais recente.
 */
export function useSpeakingHistory(
  userId: number,
  courseSlug: string,
  lessonNumber: number,
  announce: (message: string) => void,
) {
  const queryClient = useQueryClient()
  const [savedAudioUrl, setSavedAudioUrl] = useState<string | null>(null)
  const [playingAttemptId, setPlayingAttemptId] = useState<number | null>(null)

  const query = useQuery({
    queryKey: ['speaking-attempts', userId, courseSlug, lessonNumber] as const,
    queryFn: async () => {
      const { data } = await api.GET('/api/speaking/attempts', {
        params: { query: { lesson: lessonNumber, course: courseSlug } },
      })
      if (!data) throw new Error('Não foi possível carregar as gravações.')
      return data
    },
    retry: false,
    // Enquanto houver transcrição em andamento a lista se atualiza sozinha; sem
    // isso o aluno ficaria recarregando a página para ver o resultado.
    refetchInterval: (current) =>
      current.state.data?.some((attempt) =>
        ['queued', 'processing'].includes(attempt.transcription?.status ?? ''),
      ) ? 1500 : false,
  })

  useEffect(() => () => {
    if (savedAudioUrl && typeof URL.revokeObjectURL === 'function') URL.revokeObjectURL(savedAudioUrl)
  }, [savedAudioUrl])

  async function play(attempt: SpeakingAttempt) {
    announce('Carregando gravação salva…')
    try {
      const response = await authenticatedFetch(`/api/speaking/attempts/${attempt.id}/audio`)
      if (!response.ok) throw new Error('Falha ao carregar o áudio.')
      setSavedAudioUrl(URL.createObjectURL(await response.blob()))
      setPlayingAttemptId(attempt.id)
      announce('Gravação salva carregada.')
    } catch {
      announce('Não foi possível carregar essa gravação.')
    }
  }

  async function remove(attemptId: number) {
    const { response } = await api.DELETE('/api/speaking/attempts/{attempt_id}', {
      params: { path: { attempt_id: attemptId } },
    })
    if (!response.ok) {
      announce('Não foi possível excluir essa gravação.')
      return
    }
    if (playingAttemptId === attemptId) {
      setSavedAudioUrl(null)
      setPlayingAttemptId(null)
    }
    announce('Gravação excluída da sua conta.')
    await invalidateStudy(queryClient, 'speakingDelete')
  }

  async function transcribe(attemptId: number) {
    announce('Solicitando transcrição automatizada…')
    const { data, response } = await api.POST('/api/speaking/attempts/{attempt_id}/transcription', {
      params: { path: { attempt_id: attemptId } },
    })
    if (!data) {
      announce(response?.status === 429
        ? 'A cota diária de análises assistidas foi atingida.'
        : 'O provedor não está disponível. Sua gravação e autoavaliação continuam salvas.')
      await invalidateStudy(queryClient, 'assistUsage')
      return
    }
    announce('Transcrição solicitada. Este resultado será claramente marcado como automático.')
    await invalidateStudy(queryClient, 'transcriptionChange')
  }

  async function rateTranscription(jobId: number, rating: 'helpful' | 'not_helpful') {
    const { data } = await api.PUT('/api/speaking/transcriptions/{job_id}/rating', {
      params: { path: { job_id: jobId } },
      body: { rating },
    })
    announce(data
      ? 'Obrigado. Sua avaliação ajuda a decidir se o recurso pode ser liberado.'
      : 'Não foi possível salvar sua avaliação da transcrição.')
    if (data) await invalidateStudy(queryClient, 'transcriptionRating')
  }

  async function removeTranscription(jobId: number) {
    const { response } = await api.DELETE('/api/speaking/transcriptions/{job_id}', {
      params: { path: { job_id: jobId } },
    })
    if (!response.ok) {
      announce('Não foi possível excluir a transcrição.')
      return
    }
    announce('Transcrição excluída. A gravação foi mantida.')
    await invalidateStudy(queryClient, 'transcriptionChange')
  }

  return { query, savedAudioUrl, playingAttemptId, play, remove, transcribe, rateTranscription, removeTranscription }
}
