import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '../../api/client'
import { invalidateStudy } from '../../api/invalidateStudy'
import { canSyncFor } from '../../api/media'
import type { components } from '../../api/schema'
import { listLocal, readLocal, removeLocal, writeLocal } from '../../storage/local'
import { ActivityClock } from './activityClock'

type Event = components['schemas']['ActivityEventIn']

export function ActiveStudyTime({ userId, lessonId }: { userId: number; lessonId: number }) {
  const [message, setMessage] = useState('Conecte-se para iniciar a medição de tempo ativo.')
  const [warning, setWarning] = useState('')
  const queryClient = useQueryClient()
  useEffect(() => {
    let alive = true
    let starting = false
    let syncing = false
    let nextStart = 0
    let sessionId = crypto.randomUUID()
    let anchor = 0
    let clock: ActivityClock | null = null
    let lastInteraction = -Infinity
    const prefix = `aulas-ingles:activity-event:v1:${userId}:`
    const memory = new Map<string, Event>()
    const say = (text: string) => { if (alive) setMessage(text) }
    const warn = (text: string) => { if (alive) setWarning(text) }
    const load = () => {
      const keys = listLocal(prefix)
      if (!keys.ok) { warn(keys.error); return }
      for (const key of keys.value) {
        const raw = readLocal(key)
        if (!raw.ok) { warn(raw.error); continue }
        try {
          const value = JSON.parse(raw.value ?? 'null') as Event | null
          if (value && typeof value.session_id === 'string' && typeof value.operation_key === 'string'
            && key === prefix + value.operation_key && Number.isInteger(value.duration_ms)
            && value.duration_ms > 0 && value.duration_ms <= 30000 && Number.isInteger(value.end_offset_ms)
            && value.end_offset_ms >= value.duration_ms && value.end_offset_ms <= 86400000) memory.set(key, value)
          else warn('Evento local inválido preservado; parte do tempo não foi contabilizada.')
        } catch { warn('Evento local inválido preservado; parte do tempo não foi contabilizada.') }
      }
    }
    async function sync() {
      if (syncing || !alive || !canSyncFor(userId)) return
      syncing = true
      let credited = false
      let failed = false
      try {
        load()
        for (const [key, body] of memory) {
          if (!alive || !canSyncFor(userId)) return
          const { data, response } = await api.POST('/api/me/activity/events', { body })
          if (!alive || !canSyncFor(userId)) return
          if (!data) {
            failed = true
            say(response.status === 410 ? 'Há tempo pendente há mais de 7 dias; foi preservado, mas não contabilizado.'
              : 'Tempo ativo pendente de sincronização; não limpe os dados locais.')
            if (response.status === 410 || response.status === 422 || response.status === 409) continue
            break
          }
          const removed = removeLocal(key)
          if (!removed.ok) { failed = true; warn(removed.error); break }
          memory.delete(key)
          credited = true
        }
        if (!failed && clock) say(memory.size ? 'Tempo ativo pendente de sincronização.' : 'Tempo ativo sincronizado.')
        if (credited) void invalidateStudy(queryClient, 'activityCredited')
      } catch { say('Tempo ativo pendente de sincronização; confira a conexão.') }
      finally { syncing = false }
    }
    async function start() {
      if (clock || starting || !alive || !canSyncFor(userId) || performance.now() < nextStart) return
      starting = true
      nextStart = performance.now() + 30000
      try {
        const { data } = await api.POST('/api/me/activity/sessions', { body: { session_id: sessionId, lesson_id: lessonId } })
        if (!alive || !canSyncFor(userId)) return
        if (!data) { say('Não foi possível iniciar a medição de tempo ativo.'); return }
        // A âncora local começa após a resposta: latência não é tempo de estudo.
        const elapsed = Date.parse(data.server_now) - Date.parse(data.started_at)
        if (!Number.isFinite(elapsed) || elapsed < 0 || elapsed >= 86370000) {
          sessionId = crypto.randomUUID()
          return
        }
        anchor = performance.now() - elapsed
        clock = new ActivityClock(anchor, (end, duration) => {
          load()
          if (memory.size >= 5000) { warn('Fila de tempo cheia. Reconecte; novos intervalos não serão registrados.'); return }
          const body: Event = { session_id: sessionId, operation_key: crypto.randomUUID(), end_offset_ms: end, duration_ms: duration }
          const key = prefix + body.operation_key
          memory.set(key, body)
          const saved = writeLocal(key, JSON.stringify(body))
          if (!saved.ok) warn(`${saved.error} Tempo pendente apenas nesta tela; pode se perder ao sair.`)
          else say('Tempo ativo pendente de sincronização.')
          void sync()
        })
        say('Medição iniciada. Interaja com a aula para registrar tempo ativo.')
      } catch { say('Conecte-se para iniciar a medição de tempo ativo.') }
      finally { starting = false }
    }
    const interaction = () => { lastInteraction = performance.now() }
    const tick = () => {
      const now = performance.now()
      const playing = [...document.querySelectorAll('audio')].some((audio) => !audio.paused && !audio.ended)
      clock?.tick(now, document.visibilityState === 'visible' && document.hasFocus()
        && (now - lastInteraction < 120000 || playing))
      if (clock && now - anchor >= 86370000) {
        clock.flush(); clock = null; sessionId = crypto.randomUUID()
      }
      void start()
    }
    const wake = () => { tick(); void sync() }
    const pause = () => { clock?.tick(performance.now(), false) }
    const signals = ['pointerdown', 'keydown', 'scroll', 'touchstart'] as const
    signals.forEach((name) => window.addEventListener(name, interaction, { passive: true, capture: true }))
    window.addEventListener('online', wake)
    window.addEventListener('focus', wake)
    window.addEventListener('blur', pause)
    window.addEventListener('pagehide', pause)
    document.addEventListener('visibilitychange', wake)
    const timer = window.setInterval(tick, 1000)
    const retryTimer = window.setInterval(() => void sync(), 30000)
    void start(); void sync()
    return () => {
      // Persiste antes de sair; não depende de uma requisição durante unload.
      clock?.flush()
      alive = false
      clearInterval(timer); clearInterval(retryTimer)
      signals.forEach((name) => window.removeEventListener(name, interaction, true))
      window.removeEventListener('online', wake)
      window.removeEventListener('focus', wake)
      window.removeEventListener('blur', pause)
      window.removeEventListener('pagehide', pause)
      document.removeEventListener('visibilitychange', wake)
    }
  }, [userId, lessonId, queryClient])
  return <aside className="study-instructions" aria-label="Tempo ativo de estudo">
    <details><summary>Como o tempo de estudo é contado</summary>
    <p>Aba visível e em foco: interação nos últimos 2 minutos ou áudio tocando.
      Pausas e segundo plano não contam. Estimativa de atividade, não de aprendizagem.</p>
    </details>
    <p role="status">{message}</p>
    {warning && <p role="alert">{warning}</p>}
  </aside>
}
