/** Estados de carregando e de erro. Erro sempre diz o que fazer a seguir. */
import { ApiError, errorGuidance } from '../api/errors'

export function Carregando({ oque }: { oque: string }) {
  return (
    <p className="muted" role="status">
      Carregando {oque}…
    </p>
  )
}

export function Erro({ erro, aoTentarDeNovo }: { erro: Error; aoTentarDeNovo: () => void }) {
  const guidance = errorGuidance(erro)
  return (
    <div className="estado-erro" role="alert">
      <p className="erro">{guidance.message}</p>
      <p className="muted">{guidance.next}</p>
      <button type="button" onClick={aoTentarDeNovo}>Tentar de novo</button>
      <details>
        <summary>Detalhes técnicos</summary>
        {erro instanceof ApiError ? <>
          <p>{erro.message}</p>
          {erro.status !== undefined && <p>HTTP {erro.status}</p>}
          {erro.requestId && <p>Identificador: <code>{erro.requestId}</code></p>}
        </> : <p>Falha de carregamento.</p>}
      </details>
    </div>
  )
}
