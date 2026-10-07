/** Estados de carregando e de erro. Erro sempre diz o que fazer a seguir. */

export function Carregando({ oque }: { oque: string }) {
  return (
    <p className="muted" role="status">
      Carregando {oque}…
    </p>
  )
}

export function Erro({ erro, aoTentarDeNovo }: { erro: Error; aoTentarDeNovo: () => void }) {
  return (
    <div className="estado-erro" role="alert">
      <p className="erro">{erro.message}</p>
      <p className="muted">
        A API em <code>localhost:8010</code> está no ar? Tente <code>make up</code>.
      </p>
      <button onClick={aoTentarDeNovo}>Tentar de novo</button>
    </div>
  )
}
