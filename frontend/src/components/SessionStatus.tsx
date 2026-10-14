import { useSessao } from '../api/auth'

export function SessionStatus() {
  const { estado, revalidar, revalidando, aviso } = useSessao()
  const pausada = estado === 'indisponivel' || estado === 'offline'
  if (!pausada && !aviso) return null
  return (
    <div className="session-status" role="status" aria-live="polite">
      {pausada && (
        <>
          <span>
            {estado === 'offline' ? 'Você está sem conexão.' : 'A confirmação da sessão está temporariamente indisponível.'}
            {' '}A sincronização está pausada. Mantenha esta página aberta para preservar o trabalho que ainda está na tela.
          </span>
          <button type="button" disabled={revalidando} onClick={() => void revalidar()}>
            {revalidando ? 'Confirmando sessão…' : 'Tentar confirmar sessão'}
          </button>
        </>
      )}
      {aviso && <span>{aviso}</span>}
    </div>
  )
}
