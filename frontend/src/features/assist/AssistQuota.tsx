import type { components } from '../../api/schema'

export function AssistQuota({ status, modality = 'legacy' }: {
  status: components['schemas']['AssistStatusOut'] | components['schemas']['DialogueStatusOut']
  modality?: 'legacy' | 'conversation'
}) {
  return (
    <p className="assist-disclosure" role="status">
      Restam {status.remaining_today} {modality === 'conversation' ? 'turnos de conversa hoje, com cota própria.' : 'análises hoje, compartilhadas entre escrita e transcrição.'}
      {' '}{status.reserved_today} reservadas; {status.consumed_today} utilizadas.
      {' '}Renovação à meia-noite UTC. Reservas não iniciadas expiram automaticamente.
      {' '}Custo confirmado: US$ {(status.cost_microusd_today / 1_000_000).toFixed(6)}
      {status.cost_incomplete ? ' (parcial: há chamadas sem custo confirmado).' : '.'}
      {' '}Após iniciar o processamento, falhas e exclusões não devolvem a cota.
      {'transcription_enabled' in status && status.transcription_enabled && <>
        {' '}{status.worker_state === 'active'
          ? 'Processador de transcrições ativo.'
          : 'Processador de transcrições sem sinal recente; sua solicitação permanece na fila até vencer.'}
        {' '}{status.queued_jobs ?? 0} transcrições suas na fila.
        {status.oldest_queued_seconds != null && ` A mais antiga aguarda cerca de ${Math.ceil(status.oldest_queued_seconds / 60)} min.`}
      </>}
    </p>
  )
}
