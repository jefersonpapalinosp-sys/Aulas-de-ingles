import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import type { ReviewItem, ReviewItemType } from '../api/client'
import { ApiError } from '../api/errors'
import type { ReviewGradeCommand } from '../api/review'
import {
  useAvaliar,
  useDeleteReviewItem,
  useDueCards,
  useSetReviewItemStatus,
  useSuspendedReviewItems,
} from '../api/review'
import { useCourseCurriculum, useCourses } from '../api/queries'
import { Carregando, Erro } from '../components/States'
import { ReviewCard } from '../features/review/ReviewCard'
import { ReviewFilters } from '../features/review/ReviewFilters'
import { inHowLong, NOTES } from '../features/review/reviewLabels'
import { SuspendedItems } from '../features/review/SuspendedItems'
import { DEFAULT_COURSE_SLUG, todayPath } from '../routing/courseRoutes'
import { usePagedItems } from './usePagedItems'

export function ReviewPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const courseSlug = searchParams.get('course') || DEFAULT_COURSE_SLUG
  const unitSlug = searchParams.get('unit') || ''
  const courses = useCourses()
  const curriculum = useCourseCurriculum(courseSlug)
  const [itemType, setItemType] = useState<ReviewItemType | ''>('')
  const [skill, setSkill] = useState('')
  const [maxMinutes, setMaxMinutes] = useState<number | ''>('')
  const [suspendedCursor, setSuspendedCursor] = useState<string>()
  const suspendedLoadingMore = useRef(false)
  const suspendedStatusRef = useRef<HTMLParagraphElement>(null)
  const suspendedScope = useRef(`${courseSlug}:${unitSlug}`)
  const {
    data: items,
    isPending,
    error,
    refetch,
  } = useDueCards({
    courseSlug,
    unitSlug: unitSlug || undefined,
    itemType: itemType || undefined,
    skill: skill || undefined,
    maxMinutes: maxMinutes || undefined,
  })
  const suspended = useSuspendedReviewItems({
    courseSlug,
    unitSlug: unitSlug || undefined,
  }, suspendedCursor)
  const [suspendedItems, setSuspendedItems] = usePagedItems<ReviewItem>(
    suspended.data,
    suspendedCursor,
    suspendedLoadingMore,
    suspendedStatusRef,
  )
  const grade = useAvaliar()
  const setStatus = useSetReviewItemStatus()
  const deleteItem = useDeleteReviewItem()
  const [flipped, setFlipped] = useState(false)
  const [lastMessage, setLastMessage] = useState<string | null>(null)
  const [pendingGrade, setPendingGrade] = useState<{ command: ReviewGradeCommand; card: ReviewItem } | null>(null)
  const inFlight = useRef(false)
  const [gradeFailure, setGradeFailure] = useState<Error | null>(null)

  const item = pendingGrade?.card ?? items?.[0]
  const hasActivityFilters = Boolean(itemType || skill || maxMinutes)
  const hasFilters = Boolean(unitSlug || hasActivityFilters)
  const nextSuspendedCursor = suspended.data?.next_cursor

  useLayoutEffect(() => {
    const scope = `${courseSlug}:${unitSlug}`
    if (suspendedScope.current === scope) return
    suspendedScope.current = scope
    setSuspendedItems([])
    setSuspendedCursor(undefined)
    suspendedLoadingMore.current = false
  }, [courseSlug, setSuspendedItems, unitSlug])

  function setScope(nextCourse: string, nextUnit = '') {
    const next = new URLSearchParams(searchParams)
    next.set('course', nextCourse)
    if (nextUnit) next.set('unit', nextUnit)
    else next.delete('unit')
    setSearchParams(next, { replace: true })
    setFlipped(false)
    setLastMessage(null)
  }

  const answer = useCallback(
    (quality: number) => {
      if (!item || inFlight.current || (pendingGrade && !gradeFailure)) return
      if (gradeFailure instanceof ApiError && gradeFailure.status === 409) return
      const operation = pendingGrade ?? {
        card: item,
        command: { cardId: item.id, quality, idempotencyKey: crypto.randomUUID(), expectedRevision: item.revision ?? 0 },
      }
      inFlight.current = true
      setPendingGrade(operation)
      setGradeFailure(null)
      grade.mutate(
        operation.command,
        {
          onSuccess: (data) => {
            setLastMessage(`${item.prompt} volta ${inHowLong(data.interval_days)}`)
            setFlipped(false)
            setPendingGrade(null)
            inFlight.current = false
          },
          onError: (error) => { inFlight.current = false; setGradeFailure(error) },
        },
      )
    },
    [item, grade, pendingGrade, gradeFailure],
  )

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.repeat || pendingGrade || inFlight.current) return
      if (
        event.target instanceof Element &&
        event.target.closest(
          'a[href], button, input, select, textarea, summary, audio[controls], video[controls], [contenteditable="true"], [role="button"]',
        )
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
  }, [flipped, answer, pendingGrade])

  if (isPending && !pendingGrade) return <Carregando oque="a revisão de hoje" />
  if (error && !pendingGrade) return <Erro erro={error} aoTentarDeNovo={() => void refetch()} />

  function suspendCurrent() {
    if (!item) return
    setStatus.mutate(
      { itemId: item.id, status: 'suspended' },
      { onSuccess: () => {
        setLastMessage('Item suspenso. Ele saiu da fila de hoje.')
        setSuspendedItems([])
        setSuspendedCursor(undefined)
      } },
    )
    setFlipped(false)
  }

  function remove(itemId: number) {
    if (!window.confirm('Excluir este item da fila? Os recibos de revisão permanecem na conta.')) return
    deleteItem.mutate(itemId, {
      onSuccess: () => {
        setLastMessage('Item excluído da sua fila.')
        setSuspendedItems((current) => current.filter((entry) => entry.id !== itemId))
      },
    })
    setFlipped(false)
  }

  return (
    <div className="review-page">
      <p className="eyebrow">Revisão multimodal adaptativa</p>
      <h1>{item ? 'Revisar' : hasFilters ? 'Nenhum item com estes filtros' : 'Nada para revisar agora'}</h1>
      <p className="lead">
        {item
          ? `${items?.length ?? 1} ${items?.length === 1 ? 'item disponível' : 'itens disponíveis'} nesta seleção.`
          : hasFilters
            ? 'Ajuste os filtros para encontrar outras atividades vencidas.'
            : lastMessage
              ? 'Você concluiu a revisão selecionada.'
              : 'Marque uma aula como estudada ou pratique: vocabulário e erros relevantes entram aqui.'}
      </p>

      <ReviewFilters
        courseSlug={courseSlug}
        unitSlug={unitSlug}
        courses={courses.data ?? []}
        units={curriculum.data?.units ?? []}
        itemType={itemType}
        skill={skill}
        maxMinutes={maxMinutes}
        hasActivityFilters={hasActivityFilters}
        onScope={setScope}
        onItemType={(value) => { setItemType(value); setFlipped(false) }}
        onSkill={(value) => { setSkill(value); setFlipped(false) }}
        onMaxMinutes={(value) => { setMaxMinutes(value); setFlipped(false) }}
        onClear={() => { setItemType(''); setSkill(''); setMaxMinutes('') }}
      />

      {lastMessage && <p className="ultima" role="status">{lastMessage}</p>}
      {pendingGrade && <p role="status">{gradeFailure ? 'Resultado não confirmado. Sua resposta foi preservada.' : 'Confirmando revisão…'}</p>}
      {gradeFailure && pendingGrade && (
        gradeFailure instanceof ApiError && gradeFailure.status === 409
          ? <div role="alert"><p>Este item mudou em outra sessão. Confira a fila atual antes de avaliar novamente.</p>
            <button type="button" onClick={() => void refetch().then(() => {
              setPendingGrade(null); setGradeFailure(null); setFlipped(false)
            })}>Conferir fila atual</button></div>
          : <button type="button" onClick={() => answer(pendingGrade.command.quality)}>Reenviar a mesma avaliação</button>
      )}

      {item && (
        <ReviewCard
          item={item}
          flipped={flipped}
          grading={grade.isPending}
          blocked={Boolean(pendingGrade)}
          suspending={setStatus.isPending}
          removing={deleteItem.isPending}
          onFlip={() => setFlipped(true)}
          onAnswer={answer}
          onSuspend={suspendCurrent}
          onRemove={() => remove(item.id)}
        />
      )}

      <SuspendedItems
        items={suspendedItems}
        failed={Boolean(suspended.error)}
        fetching={suspended.isFetching}
        nextCursor={nextSuspendedCursor ?? undefined}
        statusRef={suspendedStatusRef}
        onReactivate={(itemId) => setStatus.mutate(
          { itemId, status: 'active' },
          { onSuccess: () => setSuspendedItems((current) =>
            current.filter((entry) => entry.id !== itemId)) },
        )}
        onRemove={remove}
        onLoadMore={(cursor) => { suspendedLoadingMore.current = true; setSuspendedCursor(cursor) }}
      />

      {!item && (
        <p className="navbtns">
          <Link className="btn ghost" to={todayPath(courseSlug)}>← Hoje e mapa</Link>
        </p>
      )}
    </div>
  )
}
