import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import type { ReviewItemType } from '../api/client'
import {
  useAvaliar,
  useDeleteReviewItem,
  useDueCards,
  useSetReviewItemStatus,
  useSuspendedReviewItems,
} from '../api/review'
import { Markdown } from '../components/Markdown'
import { Carregando, Erro } from '../components/States'

const NOTES = [
  { key: '1', label: 'Errei', quality: 1, className: 'errei' },
  { key: '2', label: 'Difícil', quality: 3, className: 'dificil' },
  { key: '3', label: 'Bom', quality: 4, className: 'bom' },
  { key: '4', label: 'Fácil', quality: 5, className: 'facil' },
] as const

const TYPE_LABELS: Record<ReviewItemType, string> = {
  vocabulary: 'Vocabulário',
  grammar_error: 'Erro gramatical',
  phrase: 'Frase',
  listening: 'Listening',
  writing_prompt: 'Escrita',
  speaking_prompt: 'Speaking',
}

function inHowLong(days: number): string {
  if (days === 1) return 'amanhã'
  if (days < 30) return `em ${days} dias`
  if (days < 365) return `em ${Math.round(days / 30)} meses`
  return `em ${(days / 365).toFixed(1)} anos`
}

function durationLabel(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  return `${Math.ceil(seconds / 60)} min`
}

export function ReviewPage() {
  const [itemType, setItemType] = useState<ReviewItemType | ''>('')
  const [skill, setSkill] = useState('')
  const [maxMinutes, setMaxMinutes] = useState<number | ''>('')
  const {
    data: items,
    isPending,
    error,
    refetch,
  } = useDueCards({
    itemType: itemType || undefined,
    skill: skill || undefined,
    maxMinutes: maxMinutes || undefined,
  })
  const suspended = useSuspendedReviewItems()
  const grade = useAvaliar()
  const setStatus = useSetReviewItemStatus()
  const deleteItem = useDeleteReviewItem()
  const [flipped, setFlipped] = useState(false)
  const [lastMessage, setLastMessage] = useState<string | null>(null)

  const item = items?.[0]
  const hasFilters = Boolean(itemType || skill || maxMinutes)

  const answer = useCallback(
    (quality: number) => {
      if (!item) return
      grade.mutate(
        { cardId: item.id, quality },
        {
          onSuccess: (data) => {
            setLastMessage(`${item.prompt} volta ${inHowLong(data.interval_days)}`)
            setFlipped(false)
          },
        },
      )
    },
    [item, grade],
  )

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (
        event.target instanceof HTMLInputElement ||
        event.target instanceof HTMLSelectElement ||
        event.target instanceof HTMLTextAreaElement ||
        event.target instanceof HTMLButtonElement
      ) {
        return
      }
      if (!flipped && (event.key === ' ' || event.key === 'Enter')) {
        event.preventDefault()
        setFlipped(true)
        return
      }
      if (flipped) {
        const note = NOTES.find((candidate) => candidate.key === event.key)
        if (note) {
          event.preventDefault()
          answer(note.quality)
        }
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [flipped, answer])

  if (isPending) return <Carregando oque="a revisão de hoje" />
  if (error) return <Erro erro={error} aoTentarDeNovo={() => void refetch()} />

  function suspendCurrent() {
    if (!item) return
    setStatus.mutate(
      { itemId: item.id, status: 'suspended' },
      { onSuccess: () => setLastMessage('Item suspenso. Ele saiu da fila de hoje.') },
    )
    setFlipped(false)
  }

  function remove(itemId: number) {
    if (!window.confirm('Excluir este item e todo o histórico de revisão dele?')) return
    deleteItem.mutate(itemId, {
      onSuccess: () => setLastMessage('Item excluído da sua fila.'),
    })
    setFlipped(false)
  }

  return (
    <div className="review-page">
      <p className="eyebrow">Revisão multimodal adaptativa</p>
      <h1>{item ? 'Revisar' : hasFilters ? 'Nenhum item com estes filtros' : 'Nada para revisar agora'}</h1>
      <p className="lead">
        {item
          ? `${items.length} ${items.length === 1 ? 'item disponível' : 'itens disponíveis'} nesta seleção.`
          : hasFilters
            ? 'Ajuste os filtros para encontrar outras atividades vencidas.'
            : lastMessage
              ? 'Você concluiu a revisão selecionada.'
              : 'Marque uma aula como estudada ou pratique: vocabulário e erros relevantes entram aqui.'}
      </p>

      <div className="review-filters" aria-label="Filtros da revisão">
        <label>
          Tipo
          <select
            value={itemType}
            onChange={(event) => {
              setItemType(event.target.value as ReviewItemType | '')
              setFlipped(false)
            }}
          >
            <option value="">Todos</option>
            {Object.entries(TYPE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
        <label>
          Competência
          <select
            value={skill}
            onChange={(event) => {
              setSkill(event.target.value)
              setFlipped(false)
            }}
          >
            <option value="">Todas</option>
            <option value="vocabulary">Vocabulário</option>
            <option value="grammar">Gramática</option>
            <option value="listening">Listening</option>
            <option value="writing">Escrita</option>
            <option value="speaking">Fala</option>
          </select>
        </label>
        <label>
          Duração
          <select
            value={maxMinutes}
            onChange={(event) => {
              setMaxMinutes(event.target.value ? Number(event.target.value) : '')
              setFlipped(false)
            }}
          >
            <option value="">Qualquer</option>
            <option value="2">Até 2 min</option>
            <option value="5">Até 5 min</option>
            <option value="10">Até 10 min</option>
          </select>
        </label>
        {hasFilters && (
          <button
            type="button"
            onClick={() => {
              setItemType('')
              setSkill('')
              setMaxMinutes('')
            }}
          >
            Limpar filtros
          </button>
        )}
      </div>

      {lastMessage && <p className="ultima" role="status">{lastMessage}</p>}

      {item && (
        <>
          <div className="review-card-meta">
            <span>{TYPE_LABELS[item.item_type]}</span>
            <span>{item.skill}</span>
            <span>{durationLabel(item.estimated_seconds)}</span>
            <span>Aula {item.lesson_number}</span>
          </div>
          <aside className="review-reason">
            <strong>Por que voltou?</strong>
            <span>{item.reason}</span>
          </aside>

          <div className={`carta review-${item.item_type}`}>
            <p className="carta-origem">Aula {item.lesson_number} · {TYPE_LABELS[item.item_type]}</p>
            <div className="carta-termo"><Markdown>{item.prompt}</Markdown></div>
            {item.prompt_note && <p className="carta-ipa">{item.prompt_note}</p>}
            {item.media_url && (
              <audio className="review-audio" controls preload="metadata" src={item.media_url}>
                Seu navegador não suporta áudio.
              </audio>
            )}

            {flipped ? (
              <div className="carta-verso">
                <div className="carta-traducao"><Markdown>{item.answer}</Markdown></div>
                {item.context && <div className="carta-exemplo"><Markdown>{item.context}</Markdown></div>}
              </div>
            ) : (
              <button className="btn virar" onClick={() => setFlipped(true)}>
                Mostrar resposta
              </button>
            )}
          </div>

          {flipped && (
            <div className="notas">
              {NOTES.map((note) => (
                <button
                  key={note.quality}
                  className={`nota ${note.className}`}
                  onClick={() => answer(note.quality)}
                  disabled={grade.isPending}
                >
                  <span className="nota-rotulo">{note.label}</span>
                  <span className="nota-tecla">{note.key}</span>
                </button>
              ))}
            </div>
          )}

          <div className="review-item-actions">
            <span>
              {flipped ? '1–4 para avaliar' : 'espaço ou enter para revelar'} ·{' '}
              {item.repetitions === 0
                ? 'primeira vez'
                : `${item.repetitions} acertos, ${item.lapses} tropeços`}
            </span>
            <button type="button" onClick={suspendCurrent} disabled={setStatus.isPending}>
              Suspender item
            </button>
            <button type="button" onClick={() => remove(item.id)} disabled={deleteItem.isPending}>
              Excluir item
            </button>
          </div>
        </>
      )}

      {(suspended.data?.length ?? 0) > 0 && (
        <section className="review-suspended">
          <div className="sec-h">
            <span className="num">PAUSA</span>
            <h2>Itens suspensos</h2>
          </div>
          <ul>
            {suspended.data?.map((suspendedItem) => (
              <li key={suspendedItem.id}>
                <div>
                  <span>{TYPE_LABELS[suspendedItem.item_type]} · Aula {suspendedItem.lesson_number}</span>
                  <strong>{suspendedItem.prompt}</strong>
                </div>
                <button
                  type="button"
                  onClick={() => setStatus.mutate({ itemId: suspendedItem.id, status: 'active' })}
                >
                  Reativar
                </button>
                <button type="button" onClick={() => remove(suspendedItem.id)}>Excluir</button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {!item && (
        <p className="navbtns">
          <Link className="btn ghost" to="/">← Hoje e mapa</Link>
        </p>
      )}
    </div>
  )
}
