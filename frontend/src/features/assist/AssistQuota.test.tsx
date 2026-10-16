import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import type { components } from '../../api/schema'
import { AssistQuota } from './AssistQuota'

it('distingue reservas, consumo, custo parcial e renovação UTC', () => {
  const status: components['schemas']['AssistStatusOut'] = {
    transcription_enabled: true, writing_enabled: true, daily_quota: 5, evaluation_only: true,
    used_today: 3, remaining_today: 2, reserved_today: 1, consumed_today: 2,
    quota_resets_at: '2026-10-15T00:00:00Z', quota_timezone: 'UTC',
    retention_days: 30, cost_microusd_today: 200, cost_incomplete: true,
    queued_jobs: 0, worker_state: 'unknown',
  }
  const view = render(<AssistQuota status={status} />)
  expect(screen.getByRole('status')).toHaveTextContent('Restam 2 análises')
  expect(screen.getByRole('status')).toHaveTextContent('1 reservadas; 2 utilizadas')
  expect(screen.getByRole('status')).toHaveTextContent('meia-noite UTC')
  expect(screen.getByRole('status')).toHaveTextContent('US$ 0.000200 (parcial')
  expect(screen.getByRole('status')).toHaveTextContent('falhas e exclusões não devolvem a cota')
  view.rerender(<AssistQuota status={{ ...status, cost_incomplete: false }} />)
  expect(screen.getByRole('status')).not.toHaveTextContent('parcial')
  view.rerender(<AssistQuota status={{ ...status, worker_state: 'stale', queued_jobs: 2, oldest_queued_seconds: 121 }} />)
  expect(screen.getByRole('status')).toHaveTextContent('sem sinal recente')
  expect(screen.getByRole('status')).toHaveTextContent('2 transcrições suas na fila')
  expect(screen.getByRole('status')).toHaveTextContent('3 min')
  view.rerender(<AssistQuota status={{ ...status, worker_state: 'active' }} />)
  expect(screen.getByRole('status')).toHaveTextContent('Processador de transcrições ativo')
})
