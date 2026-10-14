import { Component, useEffect, useRef, useState, type ReactNode } from 'react'

function isChunkError(error: unknown): boolean {
  return error instanceof Error && /ChunkLoadError|Loading chunk|dynamically imported module|Importing a module script|Failed to load module script|Unable to preload CSS/i.test(`${error.name} ${error.message}`)
}

export function RecoveryScreen({ chunk, onRetry, home, reload = () => window.location.reload() }: {
  chunk: boolean; onRetry: () => void; home?: ReactNode; reload?: () => void
}) {
  const heading = useRef<HTMLHeadingElement>(null)
  const [confirm, setConfirm] = useState(false)
  useEffect(() => { heading.current?.focus() }, [])
  return <section className="estado-erro recovery-screen" role="alert">
    <h1 ref={heading} tabIndex={-1}>{chunk ? 'Não foi possível carregar esta tela' : 'Esta área encontrou um problema'}</h1>
    {chunk && <p>Confira a conexão ou uma atualização do aplicativo.</p>}
    <p>Não apagamos rascunhos nem a fila local. Dados apenas na memória podem não ser recuperados.</p>
    {!chunk && <button type="button" onClick={onRetry}>Tentar abrir novamente</button>}
    {home}
    {!confirm ? <button type="button" onClick={() => setConfirm(true)}>Recarregar aplicativo…</button> : <div>
      <p>Copie textos ainda visíveis. Recarregar pode perder alterações não salvas. Continuar?</p>
      <button type="button" onClick={reload}>Confirmar recarga</button>
      <button type="button" onClick={() => setConfirm(false)}>Cancelar</button>
    </div>}
  </section>
}

/** Não captura eventos/promises: os fluxos assíncronos tratam os próprios erros.
 * Nenhum reload automático, limpeza de storage, telemetria ou log de respostas. */
export class ErrorBoundary extends Component<{
  children: ReactNode; resetKey?: string; home?: ReactNode
}, { failed: boolean; chunk: boolean }> {
  state = { failed: false, chunk: false }
  static getDerivedStateFromError(error: unknown) {
    return { failed: true, chunk: isChunkError(error) }
  }
  componentDidUpdate(previous: Readonly<{ resetKey?: string }>) {
    if (this.state.failed && previous.resetKey !== this.props.resetKey) {
      this.setState({ failed: false, chunk: false })
    }
  }
  render() {
    return this.state.failed
      ? <RecoveryScreen chunk={this.state.chunk} home={this.props.home}
          onRetry={() => this.setState({ failed: false, chunk: false })} />
      : this.props.children
  }
}
