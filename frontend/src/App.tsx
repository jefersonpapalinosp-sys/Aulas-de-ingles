import { useCallback, useEffect, useState } from 'react'
import { getHealth, type Health } from './api'

type State =
  | { kind: 'carregando' }
  | { kind: 'ok'; health: Health }
  | { kind: 'erro'; mensagem: string }

export default function App() {
  const [state, setState] = useState<State>({ kind: 'carregando' })

  const carregar = useCallback(() => {
    const ctrl = new AbortController()
    setState({ kind: 'carregando' })
    getHealth(ctrl.signal)
      .then((health) => setState({ kind: 'ok', health }))
      .catch((e: unknown) => {
        if (e instanceof Error && e.name === 'AbortError') return
        setState({ kind: 'erro', mensagem: e instanceof Error ? e.message : 'Erro desconhecido.' })
      })
    return () => ctrl.abort()
  }, [])

  useEffect(() => carregar(), [carregar])

  const saudavel = state.kind === 'ok' && state.health.db === 'up'

  return (
    <main>
      <header>
        <p className="kicker">Sprint 0 · Fundação</p>
        <h1>Aulas de Inglês</h1>
        <p className="lead">
          O esqueleto está de pé. Esta página não sabe nada sozinha: tudo abaixo vem do{' '}
          <code>/api/health</code> da API, que por sua vez abre uma conexão real no Postgres.
        </p>
      </header>

      <section className={`card ${saudavel ? 'ok' : state.kind === 'carregando' ? '' : 'bad'}`}>
        <div className="card-head">
          <h2>Estado da stack</h2>
          <button onClick={carregar} aria-label="Verificar novamente">
            Verificar
          </button>
        </div>

        {state.kind === 'carregando' && <p className="muted">Consultando a API…</p>}

        {state.kind === 'erro' && (
          <>
            <p className="erro">{state.mensagem}</p>
            <p className="muted">
              A API em <code>localhost:8010</code> está no ar? Tente <code>make up</code>.
            </p>
          </>
        )}

        {state.kind === 'ok' && (
          <dl>
            <div>
              <dt>API</dt>
              <dd>{state.health.status}</dd>
            </div>
            <div>
              <dt>Banco</dt>
              <dd>{state.health.db}</dd>
            </div>
            <div>
              <dt>Versão</dt>
              <dd>{state.health.version ?? '—'}</dd>
            </div>
            <div>
              <dt>Ambiente</dt>
              <dd>{state.health.env}</dd>
            </div>
          </dl>
        )}
      </section>

      <footer>
        <p>
          Próxima sprint: as 10 aulas passam a viver no banco e saem por{' '}
          <code>GET /api/lessons</code>.
        </p>
      </footer>
    </main>
  )
}
