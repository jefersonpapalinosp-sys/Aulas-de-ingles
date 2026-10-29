import { lazy, Suspense, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { READ_POLICY } from '../../api/readPolicy'
import { api, type LessonDetail } from '../../api/client'

const Workspace = lazy(() => import('./DialogueWorkspace'))

/** O status é privado e a feature fica oculta enquanto o aceite não liberar a flag. */
export function DialogueEntry({ lesson, userId }: { lesson: LessonDetail; userId: number }) {
  const [open, setOpen] = useState(false)
  const status = useQuery({
    queryKey: ['dialogue-status', userId],
    queryFn: async ({ signal }) => {
      const { data } = await api.GET('/api/speaking/dialogues/status', { signal })
      if (!data) throw new Error('Status da conversa indisponível.')
      return data
    },
    staleTime: 30_000, ...READ_POLICY,
  })
  if (!status.data?.enabled) return null
  return open ? <Suspense fallback={<p role="status">Abrindo conversa…</p>}>
    <Workspace key={`${userId}:${lesson.id}`} lesson={lesson} userId={userId} />
  </Suspense> : <section className="study-section">
    <h2>Pratique uma conversa</h2>
    <p>Converse por texto a partir desta aula. No modo Guiado, você também pode gravar sua fala.</p>
    <button type="button" className="btn" onClick={() => setOpen(true)}>Abrir parceiro de conversa</button>
  </section>
}
