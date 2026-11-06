import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { ApiError } from '../api/errors'
import { useSessao } from '../api/auth'
import { READ_POLICY } from '../api/readPolicy'
import { useOnline } from '../features/offline/useOnline'
import { useNativeLocal } from '../features/listening/useNativeLocal'

export function NativeListeningHistory({ userId }: { userId: number }) {
  const [pages, setPages] = useState<(number | undefined)[]>([undefined])
  const [slug, setSlug] = useState('')
  const online = useOnline()
  const { offline } = useSessao()
  const local = useNativeLocal(userId, online, offline)
  const history = useQuery({ queryKey: ['native-listening-history', userId, pages.at(-1), slug], ...READ_POLICY,
    enabled: online && !offline,
    queryFn: async () => {
      const { data, response } = await api.GET('/api/listening/history', { params: { query: {
        before: pages.at(-1), limit: 10, slug: slug || undefined,
      } } })
      if (!data) throw new ApiError('o histórico de listening', response)
      return data
    },
  })
  const recent = history.data?.items.find(item => !item.completed && item.available)
  return <section aria-label="Histórico de listening nativo">
    <h2>Meu histórico no aplicativo</h2>
    <p>Resultados corrigidos no aplicativo. As conclusões dos links externos continuam informadas por você.</p>
    {recent && <p><Link to={`/listening/${recent.slug}?sessao=${recent.session_id}`}>Continuar de onde parei: {recent.title}</Link></p>}
    <label>Filtrar histórico por atividade<select value={slug} onChange={event => { setSlug(event.target.value); setPages([undefined]) }}>
      <option value="">Todas</option><option value="hotel-riverside">Hospedagem</option>
      <option value="caminho-ao-museu">Orientação urbana</option><option value="sabado-com-amigos">Lazer</option>
    </select></label>
    {history.isError && <p role="alert">Histórico indisponível. <button type="button" onClick={() => void history.refetch()}>Atualizar histórico</button></p>}
    {history.data && <>
      <p>{history.data.attempts} prática(s). {history.data.first_attempt_at && `Primeira: ${new Date(history.data.first_attempt_at).toLocaleString('pt-BR')}. Última: ${new Date(history.data.last_attempt_at!).toLocaleString('pt-BR')}.`}</p>
      <ul className="listening-grid">{history.data.items.map(item => <li className="listening-card" key={item.session_id}>
        <h3>{item.title}</h3><p>Versão {item.version} · {item.completed ? 'Concluída' : 'Em andamento'}</p>
        <p>Primeiras respostas: {item.first_score}/{item.total}. Últimas tentativas: {item.latest_score}/{item.total}.</p>
        <p>{new Date(item.started_at).toLocaleString('pt-BR')}{item.support_revealed && ' · Com apoio textual'}</p>
        {item.available ? <><Link to={`/listening/${item.slug}?sessao=${item.session_id}`}>Abrir sessão</Link>{' · '}
          <Link to={`/listening/${item.slug}?sessao=${item.session_id}&erros=1`}>Revisar erros</Link></>
          : <p>Conteúdo indisponível; histórico preservado.</p>}
      </li>)}</ul>
      <nav aria-label="Páginas do histórico"><button type="button" disabled={pages.length === 1} onClick={() => setPages(old => old.slice(0, -1))}>Mais recentes</button>{' '}
        <button type="button" disabled={!history.data.next_before} onClick={() => setPages(old => [...old, history.data.next_before!])}>Mais antigas</button></nav>
    </>}
    {local.local && local.local.sessions.length > 0 && <details><summary>Sessões neste dispositivo ({local.local.sessions.length})</summary>
      <ul>{local.local.sessions.map(item => <li key={item.id}><Link to={`/listening/${item.activity.slug}?sessao=${item.id}`}>{item.activity.title} · sessão {item.id}</Link></li>)}</ul>
      <p>{local.local.commands.length} resposta(s) pendente(s). {local.error}</p>
      <button type="button" disabled={!online || offline || local.syncing} onClick={() => void local.sync()}>Sincronizar listening</button>
    </details>}
  </section>
}
