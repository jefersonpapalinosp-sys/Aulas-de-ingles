import { useEffect, useState } from 'react'
import {
  fetchRecording,
  flatItems,
  useDeleteRecording,
  useSpeakingAttempts,
  type NotebookScope,
} from '../../api/notebook'
import { SHORT_DATE, failureMessage } from './labels'
import { useAnnouncedPaging } from './paging'

type Props = {
  scope: NotebookScope
  onMessage: (message: string) => void
}

/** Gravações mantidas na conta, com reprodução sob demanda e exclusão. */
export function SpeakingHistorySection({ scope, onMessage }: Props) {
  const query = useSpeakingAttempts(scope)
  const remove = useDeleteRecording()
  const items = flatItems(query.data)
  const { statusRef, loadMore } = useAnnouncedPaging(query.fetchNextPage)
  const [playing, setPlaying] = useState<{ attemptId: number; url: string } | null>(null)

  // O blob de áudio é liberado ao trocar de gravação ou sair da seção: sem
  // isso cada escuta deixaria um objeto preso na memória da aba.
  useEffect(() => {
    if (!playing) return
    return () => URL.revokeObjectURL(playing.url)
  }, [playing])

  async function play(attemptId: number) {
    onMessage('Carregando gravação…')
    try {
      const blob = await fetchRecording(attemptId)
      setPlaying({ attemptId, url: URL.createObjectURL(blob) })
      onMessage('Gravação carregada.')
    } catch (error) {
      onMessage(failureMessage(error, 'Não foi possível carregar essa gravação.'))
    }
  }

  async function discard(attemptId: number) {
    onMessage('')
    try {
      await remove.mutateAsync(attemptId)
      if (playing?.attemptId === attemptId) setPlaying(null)
      onMessage('Gravação excluída da sua conta.')
    } catch (error) {
      onMessage(failureMessage(error, 'Não foi possível excluir essa gravação.'))
    }
  }

  return (
    <section aria-labelledby="recordings-title">
      <p className="study-kicker">Speaking</p>
      <h2 id="recordings-title">Gravações mantidas</h2>
      {query.isPending && items.length === 0 && <p className="muted">Carregando gravações…</p>}
      {query.isError && <p className="erro">Não foi possível carregar as gravações.</p>}
      {items.length === 0 && !query.isPending && !query.isError && (
        <p className="notebook-empty">Nenhuma gravação salva na conta.</p>
      )}
      <ul className="notebook-recordings">
        {items.map((attempt) => (
          <li key={attempt.id}>
            <div>
              <span>{attempt.course_title} · Aula {attempt.lesson_number}</span>
              {attempt.cue_text ? (
                <strong lang="en">{attempt.cue_text}</strong>
              ) : (
                <strong>Texto original indisponível</strong>
              )}
              <small>
                {Math.ceil(attempt.duration_ms / 1000)}s ·{' '}
                {SHORT_DATE.format(new Date(attempt.created_at))}
              </small>
            </div>
            <button type="button" onClick={() => void play(attempt.id)}>Ouvir</button>
            <button type="button" onClick={() => void discard(attempt.id)}>Excluir</button>
          </li>
        ))}
      </ul>
      {query.hasNextPage && (
        <button
          type="button"
          className="btn ghost"
          disabled={query.isFetchingNextPage}
          onClick={() => void loadMore()}
        >
          {query.isFetchingNextPage ? 'Carregando mais…' : 'Carregar mais gravações'}
        </button>
      )}
      {items.length > 0 && (
        <p ref={statusRef} tabIndex={-1} role="status" className="muted">
          {items.length} gravações carregadas.
        </p>
      )}
      {/* Gravação privada do aluno; a transcrição é opcional e requer consentimento. */}
      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
      {playing && <audio aria-label="Gravação do caderno" controls autoPlay src={playing.url} />}
    </section>
  )
}
