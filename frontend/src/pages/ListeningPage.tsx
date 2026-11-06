import { lazy, Suspense, useState } from 'react'
import { useSessao } from '../api/auth'
import { ApiError } from '../api/errors'
import {
  useListeningCatalog, useListeningConfig, useListeningProgress, useMarkListening,
  type ListeningInput, type ListeningProgress, type ListeningResource,
} from '../api/listening'
import { useOnline } from '../features/offline/useOnline'
import '../styles/listening.css'

const NativeListeningCatalog = lazy(() => import('./NativeListeningCatalog').then(m => ({ default: m.NativeListeningCatalog })))

const states = {
  not_started: 'Não iniciada', in_progress: 'Em andamento', completed: 'Concluída por mim',
} as const

function Activity({ resource, progress, userId, writable }: {
  resource: ListeningResource; progress?: ListeningProgress; userId: number; writable: boolean
}) {
  const mutation = useMarkListening(userId, resource.slug)
  const [pending, setPending] = useState<ListeningInput | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const save = (body: ListeningInput) => {
    setPending(body)
    setConfirmed(false)
    mutation.mutate(body, {
      onSuccess: () => { setPending(null); setConfirmed(true) },
      onError: (error) => { if (error instanceof ApiError && error.status === 409) setPending(null) },
    })
  }
  const state = progress?.state ?? 'not_started'
  return (
    <li className="listening-card">
      <p className="eyebrow">{resource.topic} · {resource.level}</p>
      <h2>{resource.title}</h2>
      <p>{resource.description}</p>
      <p className="muted">Fonte: {resource.source} · Conferido em {resource.checked_on.split('-').reverse().join('/')}</p>
      {resource.availability === 'available'
        ? <a href={resource.source_url} target="_blank" rel="noopener noreferrer" className="listening-source">Abrir no Test-English <span className="sr-only">(nova aba): {resource.title}</span><span aria-hidden="true"> ↗</span></a>
        : <p role="status">Link indisponível na última conferência. Seu progresso está preservado.</p>}
      <label htmlFor={`listening-${resource.slug}`}>Meu progresso em {resource.title}</label>
      <select id={`listening-${resource.slug}`} value={state}
        disabled={!writable || Boolean(pending) || mutation.isPending}
        onChange={(event) => save({ state: event.target.value as ListeningInput['state'],
          expected_revision: progress?.revision ?? 0, operation_key: crypto.randomUUID() })}>
        {Object.entries(states).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      {mutation.isPending && <p role="status">Salvando sua marcação…</p>}
      {confirmed && <p role="status">Marcação confirmada.</p>}
      {mutation.isError && <p role="alert">{mutation.error instanceof ApiError && mutation.error.status === 409
        ? 'O progresso mudou em outra aba. Confira o estado atualizado antes de marcar novamente.'
        : 'Não foi possível confirmar a marcação. Tente salvar novamente quando tiver conexão.'}</p>}
      {pending && mutation.isError && <button type="button" disabled={!writable}
        onClick={() => save(pending)}>Tentar salvar novamente</button>}
    </li>
  )
}

export function ListeningPage() {
  const { usuario, offline } = useSessao()
  const online = useOnline()
  const userId = usuario?.id ?? 0
  const config = useListeningConfig(userId)
  const enabled = config.data?.enabled === true
  const catalog = useListeningCatalog(userId, enabled)
  const progress = useListeningProgress(userId, enabled)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const current = new Map(progress.data?.map(item => [item.resource_slug, item]))
  const normalize = (text: string) => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
  const search = normalize(query.trim())
  const items = catalog.data?.filter(item =>
    normalize(`${item.title} ${item.topic} ${item.description}`).includes(search)
    && (filter === 'all' || (current.get(item.slug)?.state ?? 'not_started') === filter)) ?? []
  const failed = config.isError || catalog.isError || progress.isError
  const ready = Boolean(catalog.data && progress.data)
  const writable = online && !offline && ready && !failed && !progress.isFetching
  return (
    <section className="listening-page" aria-labelledby="listening-title">
      <p className="eyebrow">Prática complementar · A2</p>
      <h1 id="listening-title">Listening rápido</h1>
      <Suspense fallback={null}><NativeListeningCatalog userId={userId} /></Suspense>
      <p className="lead">Escolha um assunto, pratique no Test-English e marque aqui como foi.</p>
      <p>A conclusão é informada por você. Notas e tempo do site externo não são importados, e estas atividades não alteram seu progresso nos cursos VOA.</p>
      {(!online || offline) && <p role="status">Conecte-se à internet para abrir as atividades e confirmar marcações. Não há envio pendente automático.</p>}
      {failed && <div role="alert"><p>Não foi possível atualizar o catálogo ou seu progresso. As marcações estão bloqueadas até a confirmação.</p>
        <button type="button" onClick={() => { void config.refetch(); if (enabled) { void catalog.refetch(); void progress.refetch() } }}>Tentar novamente</button></div>}
      {config.isPending && <p role="status">Verificando disponibilidade…</p>}
      {config.data?.enabled === false && <p role="status">Listening rápido ainda não está disponível. Seu histórico permanece em Meus dados.</p>}
      {enabled && !ready && !failed && <p role="status">Carregando atividades e progresso…</p>}
      {enabled && ready && <>
        <div className="listening-filters">
          <label>Buscar assunto<input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Hotel, trabalho, cidade…" /></label>
          <label>Filtrar por progresso<select value={filter} onChange={event => setFilter(event.target.value)}>
            <option value="all">Todas as atividades</option>
            {Object.entries(states).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select></label>
        </div>
        <p role="status">{items.length} de {catalog.data?.length} atividades</p>
        {items.length === 0 && <p>Nenhuma atividade corresponde à busca e ao filtro.</p>}
        <ul className="listening-grid">{items.map(resource => <Activity key={resource.slug} resource={resource}
          progress={current.get(resource.slug)} userId={userId} writable={writable} />)}</ul>
      </>}
    </section>
  )
}
