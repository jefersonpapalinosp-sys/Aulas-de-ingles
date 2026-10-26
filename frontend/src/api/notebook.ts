/**
 * Camada de dados do Caderno: quatro listas paginadas e quatro escritas.
 *
 * Todas as páginas são keyset (`next_cursor` vindo do servidor) e entram no
 * `useInfiniteQuery`, que acumula no cache em vez de acumular num `useState`
 * da página. Isso é o que faz "carregar mais" sobreviver a uma revalidação e
 * dispensa o `setSpeakingEntries` manual que a exclusão de gravação usava.
 *
 * Toda falha sai como `ApiError`, que carrega o `request_id` do cabeçalho: as
 * mensagens do Caderno mostram esse identificador quando ele existe, e é por
 * ele que uma reclamação do aluno encontra a requisição no log.
 */

import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
  type InfiniteData,
} from '@tanstack/react-query'
import {
  api,
  authenticatedFetch,
  type NotebookEntry,
  type NotebookKind,
  type SpeakingAttemptPage,
} from './client'
import { ApiError } from './errors'
import { invalidateStudy } from './invalidateStudy'
import { READ_POLICY } from './readPolicy'

export type NotebookScope = { courseSlug: string; unitSlug?: string }
export type NotebookFilters = { lesson?: number; kind?: NotebookKind }

const falhou = (response: Response | undefined, oque: string): ApiError =>
  new ApiError(oque, response)

/** Páginas acumuladas viram uma lista só, na ordem em que chegaram. */
export function flatItems<T>(data: InfiniteData<{ items: T[] }> | undefined): T[] {
  return data?.pages.flatMap((page) => page.items) ?? []
}

type Cursor = string | undefined
const page = { initialPageParam: undefined as Cursor, ...READ_POLICY }
const nextCursor = (last: { next_cursor?: string | null }): Cursor =>
  last.next_cursor ?? undefined

export function useNotebookEntries(scope: NotebookScope, filters: NotebookFilters = {}) {
  return useInfiniteQuery({
    queryKey: [
      'notebook',
      scope.courseSlug,
      scope.unitSlug ?? 'all',
      filters.lesson ?? 'all',
      filters.kind ?? 'all',
    ],
    ...page,
    getNextPageParam: nextCursor,
    queryFn: async ({ pageParam }) => {
      const { data, response } = await api.GET('/api/me/notebook/page', {
        params: {
          query: {
            lesson: filters.lesson,
            kind: filters.kind,
            course: scope.courseSlug,
            unit: scope.unitSlug,
            limit: 20,
            cursor: pageParam,
          },
        },
      })
      if (!data) throw falhou(response, 'o caderno')
      return data
    },
  })
}

export function useWritingHistory(scope: NotebookScope) {
  return useInfiniteQuery({
    queryKey: ['writing-history', scope.courseSlug, scope.unitSlug ?? 'all'],
    ...page,
    getNextPageParam: nextCursor,
    queryFn: async ({ pageParam }) => {
      const { data, response } = await api.GET('/api/writing/history/page', {
        params: {
          query: {
            course: scope.courseSlug,
            unit: scope.unitSlug,
            limit: 20,
            cursor: pageParam,
          },
        },
      })
      if (!data) throw falhou(response, 'os textos e correções')
      return data
    },
  })
}

export function useSpeakingAttempts(scope: NotebookScope) {
  return useInfiniteQuery({
    queryKey: ['speaking-attempts-page', scope.courseSlug, scope.unitSlug ?? 'all'],
    ...page,
    getNextPageParam: nextCursor,
    queryFn: async ({ pageParam }) => {
      const { data, response } = await api.GET('/api/speaking/attempts/page', {
        params: {
          query: {
            course: scope.courseSlug,
            unit: scope.unitSlug,
            limit: 20,
            cursor: pageParam,
          },
        },
      })
      if (!data) throw falhou(response, 'as gravações')
      return data
    },
  })
}

/**
 * Evidências de todos os cursos, de propósito: o conteúdo histórico continua
 * consultável mesmo se a aula mudar ou for arquivada, então não é filtrado
 * pelo escopo do Caderno.
 */
export function useHistoricalEvidence() {
  return useInfiniteQuery({
    queryKey: ['historical-evidence-page'],
    ...page,
    getNextPageParam: nextCursor,
    queryFn: async ({ pageParam }) => {
      const { data, response } = await api.GET('/api/me/history/page', {
        params: { query: { limit: 20, cursor: pageParam } },
      })
      if (!data) throw falhou(response, 'o conteúdo histórico')
      return data
    },
  })
}

/** Análises salvas de uma proposta; só busca quando o detalhe está aberto. */
export function useWritingFeedbackHistory(promptId: number, enabled: boolean) {
  return useInfiniteQuery({
    queryKey: ['writing-feedback-history', promptId],
    ...page,
    enabled,
    getNextPageParam: nextCursor,
    queryFn: async ({ pageParam }) => {
      const { data, response } = await api.GET('/api/writing/prompts/{prompt_id}/feedback', {
        params: { path: { prompt_id: promptId }, query: { limit: 20, cursor: pageParam } },
      })
      if (!data) throw falhou(response, 'as análises salvas')
      return data
    },
  })
}

/**
 * Escrita no caderno nomeia o evento; quem decide o que fica velho é o mapa
 * único em `invalidateStudy.ts` — nenhum outro módulo de produção invalida
 * cache por conta própria (regra do FE-44, conferida por teste).
 */
function useNotebookInvalidation() {
  const client = useQueryClient()
  // `void` de propósito: devolver a promessa faria o `mutate` esperar o
  // refetch antes de concluir, e quem chama já trata o sucesso na hora.
  return () => {
    void invalidateStudy(client, 'notebookEntry')
  }
}

export function useCreateNotebookEntry(scope: NotebookScope) {
  const invalidate = useNotebookInvalidation()
  return useMutation({
    mutationFn: async (input: { lessonNumber: number; kind: NotebookKind; content: string }) => {
      const { data, response } = await api.POST('/api/me/notebook', {
        body: {
          course_slug: scope.courseSlug,
          lesson_number: input.lessonNumber,
          kind: input.kind,
          content: input.content,
        },
      })
      if (!data) throw falhou(response, 'a anotação')
      return data
    },
    onSuccess: invalidate,
  })
}

export function useUpdateNotebookEntry() {
  const invalidate = useNotebookInvalidation()
  return useMutation({
    mutationFn: async (entry: NotebookEntry) => {
      const { data, response } = await api.PUT('/api/me/notebook/{entry_id}', {
        params: { path: { entry_id: entry.id } },
        body: { kind: entry.kind, content: entry.content },
      })
      if (!data) throw falhou(response, 'a anotação')
      return data
    },
    onSuccess: invalidate,
  })
}

export function useDeleteNotebookEntry() {
  const invalidate = useNotebookInvalidation()
  return useMutation({
    mutationFn: async (entryId: number) => {
      const { response } = await api.DELETE('/api/me/notebook/{entry_id}', {
        params: { path: { entry_id: entryId } },
      })
      if (!response.ok) throw falhou(response, 'a exclusão da anotação')
      return entryId
    },
    onSuccess: invalidate,
  })
}

export function useDeleteRecording() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (attemptId: number) => {
      const { response } = await api.DELETE('/api/speaking/attempts/{attempt_id}', {
        params: { path: { attempt_id: attemptId } },
      })
      if (!response.ok) throw falhou(response, 'a exclusão da gravação')
      return attemptId
    },
    // O DELETE confirmado é a autoridade: a gravação sai das páginas em cache
    // na hora, sem invalidar. Invalidar aqui refaria todas as páginas já
    // carregadas só para confirmar uma remoção que o servidor acabou de
    // aceitar — e o aluno veria a lista piscar.
    onSuccess: (attemptId) => {
      // Outras listas de fala e a cota de transcrição ficam velhas: isso é do
      // mapa de eventos. Só a página já carregada aqui é editada no cache.
      void invalidateStudy(client, 'speakingDelete')
      client.setQueriesData<InfiniteData<SpeakingAttemptPage>>(
        { queryKey: ['speaking-attempts-page'] },
        (current) =>
          current && {
            ...current,
            pages: current.pages.map((item) => ({
              ...item,
              items: item.items.filter((attempt) => attempt.id !== attemptId),
            })),
          },
      )
    },
  })
}

/**
 * Downloads privados passam pelo `authenticatedFetch`, não por link público:
 * o caminho exige a mesma conta autenticada e nada é guardado no servidor.
 */
export async function fetchPersonalExport(): Promise<Blob> {
  const response = await authenticatedFetch('/api/me/export')
  if (!response.ok) throw falhou(response, 'a exportação dos seus dados')
  return response.blob()
}

export async function fetchRecording(attemptId: number): Promise<Blob> {
  const response = await authenticatedFetch(`/api/speaking/attempts/${attemptId}/audio`)
  if (!response.ok) throw falhou(response, 'essa gravação')
  return response.blob()
}
