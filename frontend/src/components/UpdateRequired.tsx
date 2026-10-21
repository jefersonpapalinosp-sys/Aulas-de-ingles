import { useSyncExternalStore } from 'react'
import { revisionRequiredSnapshot, subscribeRevisionRequired } from '../api/revisionRequired'
import { ConfirmReload } from './ErrorBoundary'

/**
 * Aviso do cutover: a API passou a exigir uma versão mais nova do cliente
 * (HTTP 428). Nenhuma recarga automática e nenhum foco roubado — o aluno pode
 * estar digitando. Rascunhos, gravações locais e fila ficam no dispositivo.
 */
export function UpdateRequired({ reload }: { reload?: () => void } = {}) {
  const required = useSyncExternalStore(subscribeRevisionRequired, revisionRequiredSnapshot)
  if (!required) return null
  return (
    <section className="session-status update-required" role="alert" aria-labelledby="update-required-title">
      <span>
        <strong id="update-required-title">Atualize o aplicativo.</strong>{' '}
        A API passou a exigir uma versão mais nova para salvar. Rascunhos, gravações locais e a
        fila de respostas foram preservados neste dispositivo e serão sincronizados depois da
        atualização.
      </span>
      <ConfirmReload reload={reload} />
    </section>
  )
}
