import { useEffect, useState } from 'react'
import type { LessonSummary, NotebookKind } from '../../api/client'
import { useCreateNotebookEntry, type NotebookScope } from '../../api/notebook'
import { KINDS, failureMessage } from './labels'

type Props = {
  scope: NotebookScope
  lessons: LessonSummary[]
  onMessage: (message: string) => void
}

const MAX = 2000

/** Entrada nova do caderno: aula, tipo e conteúdo. Não altera a aula. */
export function NotebookCompose({ scope, lessons, onMessage }: Props) {
  const [lessonNumber, setLessonNumber] = useState(0)
  const [kind, setKind] = useState<NotebookKind>('note')
  const [content, setContent] = useState('')
  const create = useCreateNotebookEntry(scope)

  // A aula escolhida precisa existir no recorte atual; ao trocar de curso ou
  // unidade, a seleção volta para a primeira aula publicada.
  useEffect(() => {
    if (!lessons.some((lesson) => lesson.number === lessonNumber)) {
      setLessonNumber(lessons[0]?.number ?? 0)
    }
  }, [lessonNumber, lessons])

  async function save() {
    if (!content.trim() || lessonNumber === 0) return
    onMessage('')
    try {
      await create.mutateAsync({ lessonNumber, kind, content })
      setContent('')
      onMessage('Anotação salva no seu caderno.')
    } catch (error) {
      onMessage(failureMessage(error, 'Não foi possível salvar a anotação.'))
    }
  }

  return (
    <section className="notebook-compose" aria-labelledby="new-note-title">
      <p className="study-kicker">Nova entrada</p>
      <h2 id="new-note-title">O que você quer lembrar?</h2>
      <div className="notebook-fields">
        <label>
          Aula
          <select
            value={lessonNumber}
            onChange={(event) => setLessonNumber(Number(event.target.value))}
          >
            {lessons.length === 0 && <option value={0}>Nenhuma aula publicada</option>}
            {lessons.map((lesson) => (
              <option key={`${lesson.course_slug}:${lesson.number}`} value={lesson.number}>
                Aula {lesson.number} · {lesson.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          Tipo
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value as NotebookKind)}
          >
            {KINDS.map((item) => (
              <option key={item.value} value={item.value}>{item.label}</option>
            ))}
          </select>
        </label>
      </div>
      <label className="notebook-editor">
        Conteúdo
        <textarea
          value={content}
          maxLength={MAX}
          placeholder="Escreva uma frase, dúvida ou observação…"
          onChange={(event) => setContent(event.target.value)}
        />
      </label>
      <div className="notebook-compose-actions">
        <span>{content.length}/{MAX}</span>
        <button
          type="button"
          className="btn"
          disabled={create.isPending || lessonNumber === 0 || !content.trim()}
          onClick={() => void save()}
        >
          {create.isPending ? 'Salvando…' : 'Salvar no caderno'}
        </button>
      </div>
    </section>
  )
}
